"""Core masking logic for the YinShield MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Dict, Iterable, List, Optional, Pattern, Tuple


STRATEGY_ORDER = {"loose": 0, "balanced": 1, "strict": 2}
COMMON_CHINESE_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄"
    "和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁"
    "杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林钟徐邱骆高夏蔡田樊胡凌霍虞"
    "万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程"
    "嵇邢滑裴陆荣翁荀羊於惠甄麴家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗"
    "山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司"
    "韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双闻莘党翟"
    "谭贡劳逄姬申扶堵冉宰郦雍郤璩桑桂濮牛寿通边扈燕冀僪浦尚农温别庄晏柴"
    "瞿阎连习容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利"
    "蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后"
    "荆红游竺权逯盖益桓公"
)

PERSON_LAST_NAMES = [
    "赵",
    "钱",
    "孙",
    "李",
    "周",
    "吴",
    "郑",
    "王",
    "冯",
    "陈",
    "褚",
    "卫",
    "蒋",
    "沈",
    "韩",
    "杨",
]
PERSON_GIVEN_NAMES = [
    "晨曦",
    "子墨",
    "雨桐",
    "思远",
    "嘉宁",
    "若溪",
    "浩然",
    "欣怡",
    "宇航",
    "可欣",
    "明轩",
    "依诺",
]
ADDRESS_ALIASES = [
    "上海市浦东新区世纪大道100号",
    "广东省深圳市南山区科技园科苑路15号",
    "浙江省杭州市余杭区文一西路18号",
    "江苏省苏州市工业园区星湖街88号",
    "四川省成都市高新区天府大道北段66号",
    "湖北省武汉市洪山区珞喻路120号",
]
COMPANY_ALIASES = [
    "上海云衡科技有限公司",
    "杭州清穹信息技术有限公司",
    "深圳远川数字科技有限公司",
    "苏州沐川软件有限公司",
    "成都星帆智能科技有限公司",
]
BANK_NAME_ALIASES = [
    "招商银行上海分行",
    "中国工商银行杭州分行",
    "中国建设银行深圳南山支行",
    "中国农业银行苏州工业园区支行",
]
ENGLISH_PERSON_ALIASES = [
    "Olivia Carter",
    "Ethan Walker",
    "Sophia Bennett",
    "Noah Parker",
    "Mia Brooks",
    "Liam Foster",
]
ENGLISH_ADDRESS_ALIASES = [
    "350 5th Ave, New York, NY 10118",
    "1 Market St, San Francisco, CA 94105",
    "233 S Wacker Dr, Chicago, IL 60606",
    "1600 Pennsylvania Ave NW, Washington, DC 20500",
]
ENGLISH_COMPANY_ALIASES = [
    "Northbridge Data Systems Inc.",
    "BlueRiver Health Technologies LLC",
    "SummitPeak Logistics Group Ltd.",
    "ClearPath Software Solutions Corp.",
    "Harborview Commercial Bank PLC",
    "Westfield General Hospital",
    "Riverton State University",
]


@dataclass(frozen=True)
class MatchRule:
    label: str
    pattern: Pattern[str]
    min_strategy: str = "balanced"


@dataclass
class ShieldSession:
    """Persistent replacement state for multi-turn masking."""

    replacements_to_originals: Dict[str, str] = field(default_factory=dict)
    originals_to_replacements: Dict[str, str] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)

    def register(self, label: str, original: str, replacement: str) -> None:
        self.replacements_to_originals[replacement] = original
        self.originals_to_replacements[original] = replacement
        self.counters[label] = max(self.counters.get(label, 0), self._extract_index(label, replacement))

    def get_replacement(self, original: str) -> Optional[str]:
        return self.originals_to_replacements.get(original)

    def to_dict(self) -> Dict[str, Dict[str, str]]:
        return {
            "replacements_to_originals": dict(self.replacements_to_originals),
            "counters": dict(self.counters),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Dict[str, str]]) -> "ShieldSession":
        replacements_to_originals = dict(payload.get("replacements_to_originals", {}))
        session = cls(replacements_to_originals=replacements_to_originals)
        session.originals_to_replacements = {
            original: replacement for replacement, original in replacements_to_originals.items()
        }
        session.counters = {
            label: int(index) for label, index in dict(payload.get("counters", {})).items()
        }
        session._sync_counters()
        return session

    @classmethod
    def load(cls, path: str) -> "ShieldSession":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=target.parent) as handle:
            handle.write(json.dumps(self.to_dict(), ensure_ascii=False, indent=2))
            temp_path = Path(handle.name)
        temp_path.replace(target)

    def clear(self) -> None:
        self.replacements_to_originals.clear()
        self.originals_to_replacements.clear()
        self.counters.clear()

    def clone(self) -> "ShieldSession":
        return ShieldSession.from_dict(self.to_dict())

    def _sync_counters(self) -> None:
        for replacement in self.replacements_to_originals:
            matched = re.fullmatch(r"<([A-Z_]+)_(\d+)>", replacement)
            if matched:
                label, index = matched.group(1), int(matched.group(2))
                self.counters[label] = max(self.counters.get(label, 0), index)

    @staticmethod
    def _extract_index(label: str, replacement: str) -> int:
        matched = re.fullmatch(rf"<{label}_(\d+)>", replacement)
        if not matched:
            return 0
        return int(matched.group(1))


class Shield:
    """Mask common Chinese PII with stable placeholders or aliases."""

    def __init__(
        self,
        mode: str = "placeholder",
        strategy: str = "balanced",
        session: Optional[ShieldSession] = None,
    ) -> None:
        if mode not in {"placeholder", "alias"}:
            raise ValueError("mode must be 'placeholder' or 'alias'")
        if strategy not in STRATEGY_ORDER:
            raise ValueError("strategy must be one of: loose, balanced, strict")

        self.mode = mode
        self.strategy = strategy
        self._session = session or ShieldSession()
        self._rules: List[MatchRule] = [
            MatchRule("ID_CARD", re.compile(r"(?<!\d)\d{17}[\dXx](?![\dXx])"), "loose"),
            MatchRule("PHONE", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"), "loose"),
            MatchRule(
                "EMAIL",
                re.compile(
                    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9._%+-])"
                ),
                "loose",
            ),
            MatchRule(
                "WECHAT",
                re.compile(
                    r"(?:(?:微信(?:号)?(?:是)?[:：]?\s*)|(?:WeChat(?:\s*ID)?[:：]?\s*))([A-Za-z][-_A-Za-z0-9]{5,19})",
                    re.IGNORECASE,
                ),
                "balanced",
            ),
            MatchRule(
                "BANK_ACCOUNT",
                re.compile(
                    r"(?:银行账号|对公账号|对私账号|账户号|开户账号|结算账号)[:：]?\s*([0-9 -]{10,30})",
                    re.IGNORECASE,
                ),
                "strict",
            ),
            MatchRule("BANK_CARD", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"), "balanced"),
            MatchRule("LANDLINE", re.compile(r"(?<!\d)(?:0\d{2,3}-?)?\d{7,8}(?!\d)"), "balanced"),
            MatchRule(
                "LICENSE_PLATE",
                re.compile(
                    r"(?:车牌(?:号)?[:：]?\s*)?([京津沪渝冀豫云辽黑湘皖鲁苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼]"
                    r"[A-Z][A-HJ-NP-Z0-9]{5,6})(?![A-Z0-9])"
                ),
                "balanced",
            ),
            MatchRule(
                "PASSPORT",
                re.compile(r"(?:护照(?:号|号码)?[:：]?\s*)([A-Z0-9]{7,17})", re.IGNORECASE),
                "balanced",
            ),
            MatchRule(
                "COMPANY_CODE",
                re.compile(r"(?:统一社会信用代码[:：]?\s*)([0-9A-Z]{18})", re.IGNORECASE),
                "balanced",
            ),
            MatchRule(
                "COMPANY_NAME",
                re.compile(
                    r"(?:公司名称[:：]?\s*|单位名称[:：]?\s*|企业名称[:：]?\s*)([\u4e00-\u9fa5A-Za-z0-9（）()]{4,40}?(?:公司|集团|工作室|事务所|中心))"
                ),
                "strict",
            ),
            MatchRule(
                "COMPANY_NAME",
                re.compile(
                    r"(?:(?:由|联系|对接|合作方|供应商|申请方|提交方|客户公司|签约方|服务方|承包方|承运方|企业为|公司为)"
                    r"\s*[：:]?\s*)"
                    r"([\u4e00-\u9fa5A-Za-z0-9（）()]{4,40}?(?:公司|集团|工作室|事务所|中心))"
                ),
                "strict",
            ),
            MatchRule(
                "COMPANY_NAME",
                re.compile(
                    r"(?:^|[，。；,\s])([\u4e00-\u9fa5A-Za-z0-9（）()]{4,40}?(?:公司|集团|工作室|事务所|中心))"
                    r"(?=(?:已|正在|负责|提交|申请|签约|对接|处理|回复|参与|承接|中标|发起))"
                ),
                "strict",
            ),
            MatchRule(
                "SSN",
                re.compile(r"(?:(?:SSN|Social Security Number)[:：]?\s*)(\d{3}-\d{2}-\d{4})", re.IGNORECASE),
                "strict",
            ),
            MatchRule(
                "BIRTHDATE",
                re.compile(
                    r"(?:(?:DOB|Date of Birth|Birth Date)[:：]?\s*)"
                    r"((?:19|20)\d{2}[-/](?:1[0-2]|0?[1-9])[-/](?:3[01]|[12]\d|0?[1-9])"
                    r"|(?:1[0-2]|0?[1-9])[-/](?:3[01]|[12]\d|0?[1-9])[-/](?:19|20)\d{2})",
                    re.IGNORECASE,
                ),
                "strict",
            ),
            MatchRule(
                "TAX_ID",
                re.compile(r"(?:(?:EIN|Employer Identification Number)[:：]?\s*)(\d{2}-\d{7})", re.IGNORECASE),
                "strict",
            ),
            MatchRule(
                "PHONE",
                re.compile(
                    r"(?:(?:phone|mobile|tel|telephone|call(?: me)? at)[:：]?\s*)"
                    r"(\+?1[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",
                    re.IGNORECASE,
                ),
                "balanced",
            ),
            MatchRule(
                "ADDRESS",
                re.compile(
                    r"(?:(?:address|ship to|send to|located at|lives at|resides at)\s*[:：]?\s*)"
                    r"("
                    r"\d{1,5}[A-Za-z]?\s+[A-Za-z0-9.\- ]{2,48}"
                    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way|Place|Pl)\.?"
                    r"(?:\s+(?:N|S|E|W|NE|NW|SE|SW))?"
                    r"(?:\s+(?:Apt|Apartment|Unit|Suite|Ste|Floor|Fl|#)\s*[A-Za-z0-9-]+)?"
                    r"(?:,\s*[A-Za-z.\- ]{2,40})?"
                    r"(?:,\s*[A-Z]{2})?"
                    r"(?:\s+\d{5}(?:-\d{4})?)?"
                    r")",
                    re.IGNORECASE,
                ),
                "balanced",
            ),
            MatchRule(
                "PERSON",
                re.compile(
                    r"(?:(?:[Mm]y name is|[Ii] am|[Ii]'m|[Cc]ontact is|[Rr]ecipient is|[Ss]igned by|[Hh]andled by|[Ss]ubmitted by|[Rr]equested by)\s+)"
                    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
                ),
                "balanced",
            ),
            MatchRule(
                "PERSON",
                re.compile(
                    r"(?:^|[,.;\s])([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
                    r"(?=\s+(?:submitted|approved|handled|reviewed|confirmed|called|replied|shipped|signed|joined))"
                ),
                "strict",
            ),
            MatchRule(
                "COMPANY_NAME",
                re.compile(
                    r"(?:(?:company is|vendor is|supplier is|partner is|customer company is|provided by|signed with|reviewed by|approved by)\s+)"
                    r"([A-Z][A-Za-z0-9&.,'-]*(?:\s+(?!(?:and|or)\b)[A-Z][A-Za-z0-9&.,'-]*){0,6}\s+(?:Bank\s+PLC|General\s+Hospital|State\s+University|Corporation|Technologies|Solutions|Systems|Company|Group|Hospital|University|Bank|Inc\.?|LLC|Ltd\.?|Corp\.?|LLP|PLC))"
                    r"(?=\s+(?:and|or)\s+|[,.;\s]|$)",
                    re.IGNORECASE,
                ),
                "strict",
            ),
            MatchRule(
                "COMPANY_NAME",
                re.compile(
                    r"(?:^|[,.;\s])([A-Z][A-Za-z0-9&.,'-]*(?:\s+(?!(?:and|or)\b)[A-Z][A-Za-z0-9&.,'-]*){0,6}\s+(?:Bank\s+PLC|General\s+Hospital|State\s+University|Corporation|Technologies|Solutions|Systems|Company|Group|Hospital|University|Bank|Inc\.?|LLC|Ltd\.?|Corp\.?|LLP|PLC))"
                    r"(?=\s+(?:submitted|approved|handled|provided|signed|delivered|contacted|responded))"
                ),
                "strict",
            ),
            MatchRule(
                "COMPANY_NAME",
                re.compile(
                    r"(?:(?:and|or|with)\s+)([A-Z][A-Za-z0-9&.,'-]*(?:\s+(?!(?:and|or)\b)[A-Z][A-Za-z0-9&.,'-]*){0,6}\s+(?:Bank\s+PLC|General\s+Hospital|State\s+University|Corporation|Technologies|Solutions|Systems|Company|Group|Hospital|University|Bank|Inc\.?|LLC|Ltd\.?|Corp\.?|LLP|PLC))"
                    r"(?=[,.;]|$)",
                    re.IGNORECASE,
                ),
                "strict",
            ),
            MatchRule(
                "ADDRESS",
                re.compile(
                    r"(?:住址(?:为|是)?[:：]?\s*)"
                    r"((?:中国)?"
                    r"(?:"
                    r"(?:北京市|上海市|天津市|重庆市)[^，。；,:：\s]{2,12}(?:区|县)"
                    r"|(?:[^，。；,:：\s]{2,8}(?:省|自治区|特别行政区))[^，。；,:：\s]{2,12}(?:市|州)[^，。；,:：\s]{2,12}(?:区|县)"
                    r")"
                    r"(?:[^，。；,:：]{0,12}?(?:镇|乡|街道|村|社区))?"
                    r"[^，。；,:：]{0,36}?"
                    r"(?:(?:路|街|道|巷|弄|大道|胡同)[^，。；,:：]{0,18}|(?:号|室|栋|单元|楼|层)[^，。；,:：]{0,14}))",
                ),
                "balanced",
            ),
            MatchRule(
                "ADDRESS",
                re.compile(
                    r"(?:(?:住在|住址(?:为|是)?[:：]?\s*|地址(?:是)?[:：]?\s*|收货地址(?:是)?[:：]?\s*|家庭住址[:：]?\s*|联系地址[:：]?\s*)"
                    r"|(?:^|[，。；,\s]))"
                    r"((?:中国)?"
                    r"(?:"
                    r"(?:北京市|上海市|天津市|重庆市)[^，。；,:：\s]{2,12}(?:区|县)"
                    r"|(?:[^，。；,:：\s]{2,8}(?:省|自治区|特别行政区))[^，。；,:：\s]{2,12}(?:市|州)[^，。；,:：\s]{2,12}(?:区|县)"
                    r")"
                    r"(?:[^，。；,:：]{0,12}?(?:镇|乡|街道|村|社区))?"
                    r"[^，。；,:：]{0,36}?"
                    r"(?:(?:路|街|道|巷|弄|大道|胡同)[^，。；,:：]{0,18}|(?:号|室|栋|单元|楼|层)[^，。；,:：]{0,14}))",
                ),
                "balanced",
            ),
            MatchRule(
                "ADDRESS",
                re.compile(
                    r"(?:(?:请(?:寄到|送到|发到)|寄到|送到|发到|送往|寄往|位于|地址在|搬到|导航到|定位在)"
                    r"\s*[：:]?\s*)"
                    r"((?:中国)?[\u4e00-\u9fa5A-Za-z0-9\s-]{3,48}"
                    r"(?:(?:区|县|镇|乡|街道|村|社区|园区|大厦|广场|小区|校区|写字楼|商务区|产业园|科技园|SOHO|路|街|道|巷|弄|大道|胡同|号院|号楼|号|室|栋|单元|楼|层|座)"
                    r"[\u4e00-\u9fa5A-Za-z0-9\s-]{0,24}))"
                ),
                "balanced",
            ),
            MatchRule(
                "PERSON",
                re.compile(
                    r"(?:(?:我叫|我是|姓名是|名字是|联系人是|联系人|收件人是|收件人|签收人是|签收人|客户是|用户是|患者是|患者|车主是|车主|户主是|户主)"
                    r"\s*[：:]?\s*)([\u4e00-\u9fa5]{2,3})"
                ),
                "balanced",
            ),
            MatchRule(
                "PERSON",
                re.compile(
                    r"(?:(?:请|由|让|找|联系|转告|通知|麻烦|安排|提醒|告知|提交人|申请人|负责人|处理人|跟进人|对接人|签收人)"
                    r"\s*[：:]?\s*)([\u4e00-\u9fa5]{2,3})"
                    r"(?=(?:[，。；、,\s]|来|去|到|前往|处理|跟进|签收|联系|对接|负责|明天|今天|尽快|稍后|马上|立即))"
                ),
                "balanced",
            ),
            MatchRule(
                "PERSON",
                re.compile(
                    r"(?:^|[，。；,\s])([\u4e00-\u9fa5]{2,3})"
                    r"(?=(?:已|正在|负责|跟进|联系|审批|签收|提交|处理|回复|到场|到会|确认|发起|提交了))"
                ),
                "strict",
            ),
            MatchRule(
                "MEDICAL_RECORD",
                re.compile(r"(?:病历号|门诊号|住院号|就诊卡号)[:：]?\s*([A-Za-z0-9-]{6,32})", re.IGNORECASE),
                "strict",
            ),
            MatchRule(
                "MEDICAL_RECORD",
                re.compile(r"(?:(?:MRN|Medical Record Number|Patient ID)[:：]?\s*)([A-Za-z0-9-]{6,32})", re.IGNORECASE),
                "strict",
            ),
            MatchRule(
                "ORDER_NO",
                re.compile(r"(?:订单号|订单编号|交易单号|流水号)[:：]?\s*([A-Za-z0-9-]{6,32})", re.IGNORECASE),
                "strict",
            ),
            MatchRule(
                "TRACKING_NO",
                re.compile(r"(?:快递单号|运单号|物流单号)[:：]?\s*([A-Za-z0-9-]{8,32})", re.IGNORECASE),
                "strict",
            ),
            MatchRule(
                "TRACKING_NO",
                re.compile(
                    r"(?:(?:tracking(?: number| no\.?)?|waybill|shipment id)[:：]?\s*)([A-Za-z0-9-]{8,32})",
                    re.IGNORECASE,
                ),
                "strict",
            ),
            MatchRule(
                "BIRTHDATE",
                re.compile(
                    r"(?:生日|出生日期|出生时间|出生于)[:：]?\s*"
                    r"("
                    r"(?:19|20)\d{2}[-/.年](?:1[0-2]|0?[1-9])[-/.月](?:3[01]|[12]\d|0?[1-9])(?:日)?"
                    r"|(?:1[0-2]|0?[1-9])[-/.月](?:3[01]|[12]\d|0?[1-9])(?:日)?"
                    r")"
                ),
                "strict",
            ),
            MatchRule(
                "IP_ADDRESS",
                re.compile(
                    r"(?:(?:IP(?:地址)?|IPv4|服务器IP|客户端IP|登录IP)[:：]?\s*)"
                    r"((?:\d{1,3}\.){3}\d{1,3})",
                    re.IGNORECASE,
                ),
                "strict",
            ),
            MatchRule(
                "VIN",
                re.compile(
                    r"(?:VIN|车架号|车辆识别代号)[:：]?\s*([A-HJ-NPR-Z0-9]{17})",
                    re.IGNORECASE,
                ),
                "strict",
            ),
            MatchRule(
                "TAX_ID",
                re.compile(
                    r"(?:税号|纳税人识别号|税务登记号|TIN)[:：]?\s*([0-9A-Z]{15,20})",
                    re.IGNORECASE,
                ),
                "strict",
            ),
            MatchRule(
                "BANK_NAME",
                re.compile(
                    r"(?:开户行|开户银行|收款银行)[:：]?\s*"
                    r"([\u4e00-\u9fa5A-Za-z0-9（）()]{4,40}(?:银行|支行|分行|营业部))"
                ),
                "strict",
            ),
            MatchRule(
                "CUSTOMER_ID",
                re.compile(r"(?:客户号|客户编号|客户ID)[:：]?\s*([A-Za-z0-9-]{4,32})", re.IGNORECASE),
                "strict",
            ),
            MatchRule(
                "MEMBER_ID",
                re.compile(r"(?:会员号|会员编号|会员ID)[:：]?\s*([A-Za-z0-9-]{4,32})", re.IGNORECASE),
                "strict",
            ),
            MatchRule(
                "CONTRACT_NO",
                re.compile(r"(?:合同号|合同编号|协议号)[:：]?\s*([A-Za-z0-9-]{4,40})", re.IGNORECASE),
                "strict",
            ),
        ]

    @property
    def session(self) -> ShieldSession:
        return self._session

    def new_session(self) -> ShieldSession:
        return ShieldSession()

    def load_session(self, path: str) -> ShieldSession:
        self._session = ShieldSession.load(path)
        return self._session

    def save_session(self, path: str) -> None:
        self._session.save(path)

    def reset_session(self) -> None:
        self._session.clear()

    def mask(
        self,
        text: str,
        mapping: Optional[Dict[str, str]] = None,
        session: Optional[ShieldSession] = None,
    ) -> Tuple[str, Dict[str, str]]:
        """Return masked text and replacement-to-original mapping."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        active_session = self._resolve_session(mapping, session)
        masked_text = text
        for rule in self._active_rules():
            masked_text = self._apply_rule(masked_text, rule, active_session)
        masked_text = self._apply_known_replacements(masked_text, active_session)

        return masked_text, dict(active_session.replacements_to_originals)

    def unmask(
        self,
        text: str,
        mapping: Optional[Dict[str, str]] = None,
        session: Optional[ShieldSession] = None,
    ) -> str:
        """Restore replacements in *text* using the provided or active mapping."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        if mapping is not None:
            replacements = dict(mapping)
        else:
            active_session = session or self._session
            replacements = active_session.replacements_to_originals

        restored = text
        for replacement in sorted(replacements, key=len, reverse=True):
            restored = restored.replace(replacement, replacements[replacement])
        return restored

    def _resolve_session(
        self,
        mapping: Optional[Dict[str, str]],
        session: Optional[ShieldSession],
    ) -> ShieldSession:
        if session is not None:
            return session
        if mapping is None:
            return self._session
        return ShieldSession.from_dict({"replacements_to_originals": mapping})

    def _active_rules(self) -> Iterable[MatchRule]:
        current = STRATEGY_ORDER[self.strategy]
        for rule in self._rules:
            if STRATEGY_ORDER[rule.min_strategy] <= current:
                yield rule

    def _apply_rule(self, text: str, rule: MatchRule, session: ShieldSession) -> str:
        parts: List[str] = []
        cursor = 0

        for match in rule.pattern.finditer(text):
            start, end = match.span()
            candidate = self._extract_candidate(match)
            if not candidate or not self._is_valid_candidate(rule.label, candidate):
                continue
            if candidate in session.replacements_to_originals:
                continue
            if any(existing in candidate for existing in session.replacements_to_originals):
                continue

            replacement = session.get_replacement(candidate)
            if replacement is None:
                replacement = self._make_replacement(rule.label, candidate, session)
                session.register(rule.label, candidate, replacement)

            replacement_text = self._build_replacement(match, candidate, replacement)
            parts.append(text[cursor:start])
            parts.append(replacement_text)
            cursor = end

        if cursor == 0:
            return text

        parts.append(text[cursor:])
        return "".join(parts)

    def _make_replacement(self, label: str, original: str, session: ShieldSession) -> str:
        if self.mode == "placeholder":
            session.counters[label] = session.counters.get(label, 0) + 1
            return f"<{label}_{session.counters[label]}>"

        for salt in range(128):
            candidate = self._alias_for(label, original, salt)
            if (
                candidate != original
                and candidate not in session.replacements_to_originals
                and candidate not in session.originals_to_replacements
            ):
                return candidate
        session.counters[label] = session.counters.get(label, 0) + 1
        return f"<{label}_{session.counters[label]}>"

    @staticmethod
    def _apply_known_replacements(text: str, session: ShieldSession) -> str:
        updated = text
        for original in sorted(session.originals_to_replacements, key=len, reverse=True):
            replacement = session.originals_to_replacements[original]
            if original != replacement:
                updated = updated.replace(original, replacement)
        return updated

    def _alias_for(self, label: str, original: str, salt: int) -> str:
        if label == "PERSON":
            return self._alias_person(original, salt)
        if label == "ADDRESS":
            if re.search(r"[A-Za-z]", original):
                return self._pick_from_list(ENGLISH_ADDRESS_ALIASES, original, salt)
            return self._pick_from_list(ADDRESS_ALIASES, original, salt)
        if label == "COMPANY_NAME":
            if re.search(r"[A-Za-z]", original):
                return self._pick_from_list(ENGLISH_COMPANY_ALIASES, original, salt)
            return self._pick_from_list(COMPANY_ALIASES, original, salt)
        if label == "BANK_NAME":
            return self._pick_from_list(BANK_NAME_ALIASES, original, salt)
        if label == "EMAIL":
            return self._alias_email(original, salt)
        if label == "WECHAT":
            return self._alias_wechat(original, salt)
        if label == "PHONE":
            return self._alias_mobile(original, salt)
        if label == "LANDLINE":
            return self._alias_landline(original, salt)
        if label == "BIRTHDATE":
            return self._alias_birthdate(original, salt)
        if label == "IP_ADDRESS":
            return self._alias_ip(original, salt)
        if label == "BANK_CARD":
            return self._alias_digits(original, salt, prefix="62")
        if label == "BANK_ACCOUNT":
            return self._alias_digits(original, salt)
        if label == "ID_CARD":
            return self._alias_digits(original, salt)
        if label == "SSN":
            return self._alias_ssn(original, salt)
        if label == "LICENSE_PLATE":
            return self._alias_plate(original, salt)
        if label in {
            "PASSPORT",
            "COMPANY_CODE",
            "MEDICAL_RECORD",
            "ORDER_NO",
            "TRACKING_NO",
            "VIN",
            "TAX_ID",
            "CUSTOMER_ID",
            "MEMBER_ID",
            "CONTRACT_NO",
        }:
            return self._alias_alnum(original, salt)
        return self._alias_alnum(original, salt)

    def _alias_person(self, original: str, salt: int) -> str:
        if re.search(r"[A-Za-z]", original):
            return self._pick_from_list(ENGLISH_PERSON_ALIASES, original, salt)
        last_name = self._pick_from_list(PERSON_LAST_NAMES, original, salt)
        given_name = self._pick_from_list(PERSON_GIVEN_NAMES, f"{original}:given", salt)
        alias = f"{last_name}{given_name}"
        if len(original) == 2:
            return alias[:2]
        if len(original) == 3:
            return alias[:3]
        return alias[: min(4, len(alias))]

    def _alias_email(self, original: str, salt: int) -> str:
        local, _, domain = original.partition("@")
        seed = self._seed(f"EMAIL:{original}:{salt}")
        new_local = f"user{seed % 100000:05d}"
        return f"{new_local}@{domain}"

    def _alias_wechat(self, original: str, salt: int) -> str:
        seed = self._seed(f"WECHAT:{original}:{salt}")
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789_"
        chars = ["w"]
        for index in range(max(5, len(original) - 1)):
            chars.append(alphabet[(seed + index * 11) % len(alphabet)])
        return "".join(chars)[: max(6, len(original))]

    def _alias_mobile(self, original: str, salt: int) -> str:
        seed = self._seed(f"PHONE:{original}:{salt}")
        prefix = ["13", "15", "17", "18", "19"][seed % 5]
        return prefix + "".join(str((seed // (idx + 1)) % 10) for idx in range(9))

    def _alias_landline(self, original: str, salt: int) -> str:
        digits = re.sub(r"\D", "", original)
        seed = self._seed(f"LANDLINE:{original}:{salt}")
        if len(digits) >= 11:
            area_len = 4
        else:
            area_len = 3
        area = "0" + "".join(str((seed // (idx + 3)) % 10) for idx in range(area_len - 1))
        number = "".join(str((seed // (idx + 7)) % 10) for idx in range(len(digits) - area_len))
        return f"{area}-{number}"

    def _alias_birthdate(self, original: str, salt: int) -> str:
        seed = self._seed(f"BIRTHDATE:{original}:{salt}")
        year = 1980 + seed % 30
        month = 1 + (seed // 7) % 12
        day = 1 + (seed // 13) % 28

        if "年" in original:
            return f"{year}年{month:02d}月{day:02d}日"
        if "/" in original:
            if len(original.split("/")[0]) <= 2:
                return f"{month:02d}/{day:02d}"
            return f"{year:04d}/{month:02d}/{day:02d}"
        if "." in original:
            if len(original.split(".")[0]) <= 2:
                return f"{month:02d}.{day:02d}"
            return f"{year:04d}.{month:02d}.{day:02d}"
        if "-" in original:
            if len(original.split("-")[0]) <= 2:
                return f"{month:02d}-{day:02d}"
            return f"{year:04d}-{month:02d}-{day:02d}"
        return f"{year:04d}-{month:02d}-{day:02d}"

    def _alias_ip(self, original: str, salt: int) -> str:
        seed = self._seed(f"IP:{original}:{salt}")
        octets = [10, 1 + (seed % 223), 1 + ((seed // 5) % 254), 1 + ((seed // 11) % 254)]
        return ".".join(str(part) for part in octets)

    def _alias_ssn(self, original: str, salt: int) -> str:
        seed = self._seed(f"SSN:{original}:{salt}")
        parts = [
            f"{seed % 900 + 100:03d}",
            f"{(seed // 7) % 90 + 10:02d}",
            f"{(seed // 13) % 9000 + 1000:04d}",
        ]
        return "-".join(parts)

    def _alias_digits(self, original: str, salt: int, prefix: Optional[str] = None) -> str:
        digits = re.sub(r"\D", "", original)
        seed = self._seed(f"DIGITS:{original}:{salt}")
        generated = "".join(str((seed // (idx + 5)) % 10) for idx in range(len(digits)))
        if prefix:
            generated = (prefix + generated)[0 : len(digits)]
        formatted = self._restore_non_digits(original, generated)
        return formatted

    def _alias_plate(self, original: str, salt: int) -> str:
        provinces = "京沪粤浙苏川鄂陕闽鲁"
        letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        tail = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        seed = self._seed(f"PLATE:{original}:{salt}")
        chars = [
            provinces[seed % len(provinces)],
            letters[(seed // 7) % len(letters)],
        ]
        for idx in range(len(original) - 2):
            chars.append(tail[(seed // (idx + 11)) % len(tail)])
        return "".join(chars)[: len(original)]

    def _alias_alnum(self, original: str, salt: int) -> str:
        seed = self._seed(f"ALNUM:{original}:{salt}")
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        chars: List[str] = []
        for index, char in enumerate(original):
            if char.isdigit():
                chars.append(str((seed // (index + 3)) % 10))
            elif char.isalpha():
                chars.append(alphabet[(seed // (index + 5)) % len(alphabet)])
            else:
                chars.append(char)
        return "".join(chars)

    @staticmethod
    def _restore_non_digits(original: str, generated_digits: str) -> str:
        digits_iter = iter(generated_digits)
        chars: List[str] = []
        for char in original:
            if char.isdigit():
                chars.append(next(digits_iter))
            elif char in {"X", "x"}:
                chars.append("X")
            else:
                chars.append(char)
        return "".join(chars)

    @staticmethod
    def _pick_from_list(candidates: List[str], original: str, salt: int) -> str:
        index = Shield._seed(f"{original}:{salt}") % len(candidates)
        return candidates[index]

    @staticmethod
    def _extract_candidate(match: re.Match[str]) -> str:
        if match.lastindex:
            return match.group(match.lastindex)
        return match.group(0)

    @staticmethod
    def _build_replacement(match: re.Match[str], candidate: str, replacement: str) -> str:
        whole = match.group(0)
        if whole == candidate:
            return replacement
        return whole.replace(candidate, replacement, 1)

    @staticmethod
    def _seed(value: str) -> int:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return int(digest[:12], 16)

    @staticmethod
    def _is_valid_candidate(label: str, candidate: str) -> bool:
        if label == "BANK_CARD":
            digits_only = re.sub(r"\D", "", candidate)
            return 13 <= len(digits_only) <= 19 and not re.fullmatch(r"\d{17}[\dXx]", digits_only)
        if label == "LANDLINE":
            digits_only = re.sub(r"\D", "", candidate)
            return len(digits_only) >= 10 and digits_only.startswith("0")
        if label == "PERSON":
            if re.search(r"[A-Za-z]", candidate) and not re.search(r"[\u4e00-\u9fa5]", candidate):
                return Shield._looks_like_english_person(candidate)
            return (
                candidate not in {"用户", "客户", "患者", "车主", "户主", "联系人", "收件人", "大家", "我们", "你们"}
                and 2 <= len(candidate) <= 3
                and candidate[0] in COMMON_CHINESE_SURNAMES
            )
        if label == "COMPANY_NAME":
            if re.search(r"[A-Za-z]", candidate) and not re.search(r"[\u4e00-\u9fa5]", candidate):
                return Shield._looks_like_english_company_name(candidate)
            return Shield._looks_like_company_name(candidate)
        if label == "ADDRESS":
            if re.search(r"[A-Za-z]", candidate) and not re.search(r"[\u4e00-\u9fa5]", candidate):
                return Shield._looks_like_english_address(candidate)
            return Shield._looks_like_address(candidate)
        if label == "BIRTHDATE":
            return bool(re.search(r"\d", candidate))
        if label == "IP_ADDRESS":
            parts = candidate.split(".")
            return len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)
        if label in {"ORDER_NO", "TRACKING_NO", "MEDICAL_RECORD"}:
            return any(char.isdigit() for char in candidate)
        if label in {"TAX_ID", "VIN", "CUSTOMER_ID", "MEMBER_ID", "CONTRACT_NO"}:
            return any(char.isdigit() for char in candidate)
        if label == "BANK_ACCOUNT":
            digits_only = re.sub(r"\D", "", candidate)
            return 10 <= len(digits_only) <= 30
        if label == "SSN":
            return bool(re.fullmatch(r"\d{3}-\d{2}-\d{4}", candidate))
        return True

    @staticmethod
    def _looks_like_address(candidate: str) -> bool:
        marker_patterns = [
            r"(?:省|自治区|特别行政区|市|州|区|县)",
            r"(?:镇|乡|街道|村|社区|园区|大厦|广场|小区|校区|写字楼|商务区|产业园|科技园|SOHO)",
            r"(?:路|街|道|巷|弄|大道|胡同)",
            r"(?:号院|号楼|号|室|栋|单元|楼|层|座)",
        ]
        marker_hits = sum(1 for pattern in marker_patterns if re.search(pattern, candidate))
        has_digits = bool(re.search(r"\d", candidate))
        return marker_hits >= 2 or (marker_hits >= 1 and has_digits)

    @staticmethod
    def _looks_like_company_name(candidate: str) -> bool:
        if not re.search(r"(?:公司|集团|工作室|事务所|中心)$", candidate):
            return False
        if candidate in {"会议中心", "活动中心", "培训中心", "服务中心", "客服中心", "接待中心"}:
            return False
        if re.search(r"(?:公司|集团|工作室|事务所)$", candidate):
            return len(candidate) >= 4
        return bool(
            re.search(
                r"(?:科技|信息|网络|软件|数字|智能|电子|实业|商贸|咨询|医疗|健康|工业|制造|传媒|物流|供应链|服务|研究)",
                candidate,
            )
        )

    @staticmethod
    def _looks_like_english_person(candidate: str) -> bool:
        tokens = candidate.split()
        if len(tokens) < 2 or len(tokens) > 3:
            return False
        return all(re.fullmatch(r"[A-Z][a-z]+", token) for token in tokens)

    @staticmethod
    def _looks_like_english_address(candidate: str) -> bool:
        return bool(
            re.search(r"\d", candidate)
            and re.search(
                r"\b(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way|Place|Pl)\b\.?",
                candidate,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _looks_like_english_company_name(candidate: str) -> bool:
        if re.search(r"\b(?:opened|responded|today|quickly|submitted|approved|handled|provided|signed|delivered|contacted)\b", candidate, re.IGNORECASE):
            return False
        if re.search(r"\b(?:and|or)\b", candidate, re.IGNORECASE):
            return False
        return bool(
            re.search(
                r"\b(?:Bank\s+PLC|General\s+Hospital|State\s+University|Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|Company|Group|Systems|Solutions|Technologies|LLP|PLC|Bank|Hospital|University)\b",
                candidate,
                re.IGNORECASE,
            )
            and len(candidate) >= 6
            and len(candidate.split()) >= 2
        )
