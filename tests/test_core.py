from pathlib import Path
import tempfile
import unittest

from yinshield import Shield, ShieldSession


class ShieldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shield = Shield()

    def test_mask_and_unmask_common_pii(self) -> None:
        text = (
            "我叫张三，身份证110101199001011234，手机号13812345678，"
            "邮箱test@example.com，微信号是abcde12345，住在北京市朝阳区建国路88号。"
        )

        masked, mapping = self.shield.mask(text)

        self.assertIn("<PERSON_1>", masked)
        self.assertIn("<ID_CARD_1>", masked)
        self.assertIn("<PHONE_1>", masked)
        self.assertIn("<EMAIL_1>", masked)
        self.assertIn("<WECHAT_1>", masked)
        self.assertIn("<ADDRESS_1>", masked)
        self.assertEqual(self.shield.unmask(masked, mapping), text)

    def test_reuses_same_placeholder_for_same_value(self) -> None:
        text = "我是李四，李四的手机号是13900001111，请联系13900001111。"

        masked, mapping = self.shield.mask(text)

        self.assertEqual(masked.count("<PHONE_1>"), 2)
        self.assertEqual(mapping["<PHONE_1>"], "13900001111")

    def test_masks_more_chinese_pii_patterns(self) -> None:
        text = (
            "收件人：王小明，收货地址：浙江省杭州市西湖区文三路90号2单元，"
            "座机0571-87654321，银行卡6222020202020202020，"
            "车牌京A12345，护照号E12345678，"
            "统一社会信用代码91330106MA27XG019Q，"
            "公司名称：杭州云盾科技有限公司，"
            "病历号MR20240324001，订单号20240324ABC123，快递单号SF1234567890。"
        )

        strict_shield = Shield(strategy="strict")
        masked, mapping = strict_shield.mask(text)

        for label in [
            "PERSON",
            "ADDRESS",
            "LANDLINE",
            "BANK_CARD",
            "LICENSE_PLATE",
            "PASSPORT",
            "COMPANY_CODE",
            "COMPANY_NAME",
            "MEDICAL_RECORD",
            "ORDER_NO",
            "TRACKING_NO",
        ]:
            self.assertTrue(any(key.startswith(f"<{label}_") for key in mapping))
        self.assertEqual(strict_shield.unmask(masked, mapping), text)

    def test_masks_additional_business_and_device_identifiers(self) -> None:
        text = (
            "生日：1992-08-16，登录IP：192.168.10.23，"
            "车架号：LFV3A24G9H1234567，纳税人识别号：91330100MA27XG019Q，"
            "开户银行：中国建设银行深圳南山支行，银行账号：6222 0212 3456 7890 123，"
            "客户号：KH-2024-9981，会员号：VIP-778899，合同编号：HT2024-SZ-0099。"
        )

        strict_shield = Shield(strategy="strict")
        masked, mapping = strict_shield.mask(text)

        for label in [
            "BIRTHDATE",
            "IP_ADDRESS",
            "VIN",
            "TAX_ID",
            "BANK_NAME",
            "BANK_ACCOUNT",
            "CUSTOMER_ID",
            "MEMBER_ID",
            "CONTRACT_NO",
        ]:
            self.assertTrue(any(key.startswith(f"<{label}_") for key in mapping))
        self.assertEqual(strict_shield.unmask(masked, mapping), text)

    def test_alias_mode_masks_new_explicit_business_fields(self) -> None:
        shield = Shield(mode="alias", strategy="strict")
        first, _ = shield.mask("登录IP：192.168.10.23，合同编号：HT2024-SZ-0099。")
        second, _ = shield.mask("请继续处理合同编号：HT2024-SZ-0099，对应登录IP：192.168.10.23。")

        self.assertNotIn("192.168.10.23", first)
        self.assertNotIn("HT2024-SZ-0099", first)
        self.assertEqual(shield.unmask(second), "请继续处理合同编号：HT2024-SZ-0099，对应登录IP：192.168.10.23。")

    def test_masks_people_in_natural_sentences_with_context(self) -> None:
        masked, mapping = Shield(strategy="balanced").mask("请张三明天到会，由王小明跟进，转告李四尽快处理。")

        self.assertIn("<PERSON_1>", masked)
        self.assertIn("<PERSON_2>", masked)
        self.assertIn("<PERSON_3>", masked)
        self.assertEqual(len([key for key in mapping if key.startswith("<PERSON_")]), 3)

    def test_masks_shorter_contextual_addresses(self) -> None:
        text = "请发到朝阳区酒仙桥路6号院3号楼，签收人是王小明。"
        masked, mapping = Shield(strategy="balanced").mask(text)

        self.assertIn("<ADDRESS_1>", masked)
        self.assertIn("<PERSON_1>", masked)
        self.assertEqual(Shield(strategy="balanced").unmask(masked, mapping), text)

    def test_does_not_mask_generic_pronouns_as_people(self) -> None:
        masked, mapping = Shield(strategy="balanced").mask("请大家明天到会，联系用户处理问题。")

        self.assertEqual(masked, "请大家明天到会，联系用户处理问题。")
        self.assertFalse(any(key.startswith("<PERSON_") for key in mapping))

    def test_masks_people_in_subject_predicate_sentences_under_strict(self) -> None:
        text = "王小明已提交申请，李四负责审批，张三正在跟进。"
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertEqual(len([key for key in mapping if key.startswith("<PERSON_")]), 3)
        self.assertIn("<PERSON_1>", masked)
        self.assertIn("<PERSON_2>", masked)
        self.assertIn("<PERSON_3>", masked)

    def test_masks_building_style_addresses(self) -> None:
        text = "公司位于望京SOHO T3 A座12层，请由王小明前往。"
        masked, mapping = Shield(strategy="balanced").mask(text)

        self.assertIn("<ADDRESS_1>", masked)
        self.assertIn("<PERSON_1>", masked)
        self.assertEqual(Shield(strategy="balanced").unmask(masked, mapping), text)

    def test_masks_company_names_in_natural_sentences_under_strict(self) -> None:
        text = "杭州云盾科技有限公司已提交申请，请联系深圳远川数字科技有限公司对接。"
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertEqual(len([key for key in mapping if key.startswith("<COMPANY_NAME_")]), 2)
        self.assertIn("<COMPANY_NAME_1>", masked)
        self.assertIn("<COMPANY_NAME_2>", masked)

    def test_does_not_mask_generic_centers_as_company_names(self) -> None:
        text = "活动中心已开放，会议中心正在布展，请大家按时到场。"
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertEqual(masked, text)
        self.assertFalse(any(key.startswith("<COMPANY_NAME_") for key in mapping))

    def test_masks_english_explicit_fields(self) -> None:
        text = (
            "My name is John Smith, phone: +1 (415) 555-0123, "
            "SSN: 123-45-6789, address: 1 Market St, San Francisco, CA 94105."
        )
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertIn("<PERSON_1>", masked)
        self.assertIn("<PHONE_1>", masked)
        self.assertIn("<SSN_1>", masked)
        self.assertIn("<ADDRESS_1>", masked)
        self.assertEqual(Shield(strategy="strict").unmask(masked, mapping), text)

    def test_masks_english_natural_sentences_under_strict(self) -> None:
        text = "John Smith submitted the request, and BlueRiver Health Technologies LLC approved it."
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertIn("<PERSON_1>", masked)
        self.assertIn("<COMPANY_NAME_1>", masked)
        self.assertEqual(Shield(strategy="strict").unmask(masked, mapping), text)

    def test_masks_mixed_chinese_and_english_content(self) -> None:
        text = (
            "联系人：王小明。My name is John Smith, phone: +1 415-555-0123, "
            "收货地址：北京市朝阳区建国路88号，address: 350 5th Ave, New York, NY 10118."
        )
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertIn("<PERSON_1>", masked)
        self.assertIn("<PERSON_2>", masked)
        self.assertGreaterEqual(len([key for key in mapping if key.startswith("<ADDRESS_")]), 2)
        self.assertEqual(Shield(strategy="strict").unmask(masked, mapping), text)

    def test_does_not_mask_generic_english_phrases_as_people(self) -> None:
        text = "Please Contact Support immediately. Activity Center opened today."
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertEqual(masked, text)
        self.assertFalse(any(key.startswith("<PERSON_") for key in mapping))

    def test_masks_english_address_with_unit_and_company_variants(self) -> None:
        text = (
            "Ship to: 221B Baker St Apt 5, Boston, MA 02108. "
            "Signed with Harborview Commercial Bank PLC and Westfield General Hospital."
        )
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertIn("<ADDRESS_1>", masked)
        self.assertGreaterEqual(len([key for key in mapping if key.startswith("<COMPANY_NAME_")]), 2)
        self.assertEqual(Shield(strategy="strict").unmask(masked, mapping), text)

    def test_does_not_mask_generic_english_titles_as_company_names(self) -> None:
        text = "The University opened today and the Hospital responded quickly."
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertEqual(masked, text)
        self.assertFalse(any(key.startswith("<COMPANY_NAME_") for key in mapping))

    def test_masks_english_high_frequency_identifiers(self) -> None:
        text = (
            "DOB: 1991-04-23, EIN: 12-3456789, MRN: MRN-778899, "
            "tracking number: 1Z999AA10123456784."
        )
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertIn("<BIRTHDATE_1>", masked)
        self.assertIn("<TAX_ID_1>", masked)
        self.assertIn("<MEDICAL_RECORD_1>", masked)
        self.assertIn("<TRACKING_NO_1>", masked)
        self.assertEqual(Shield(strategy="strict").unmask(masked, mapping), text)

    def test_alias_mode_avoids_colliding_with_other_original_entities(self) -> None:
        text = "Company is Northbridge Data Systems Inc., vendor is BlueRiver Health Technologies LLC."
        shield = Shield(mode="alias", strategy="strict")
        masked, mapping = shield.mask(text)

        self.assertEqual(len(mapping), 2)
        self.assertEqual(shield.unmask(masked, mapping), text)

    def test_masks_english_address_with_directional_suffix(self) -> None:
        text = "ship to: 1600 Pennsylvania Ave NW, Washington, DC 20500."
        masked, mapping = Shield(strategy="strict").mask(text)

        self.assertIn("<ADDRESS_1>", masked)
        self.assertEqual(Shield(strategy="strict").unmask(masked, mapping), text)

    def test_strategy_controls_aggressiveness(self) -> None:
        text = "订单号20240324ABC123，快递单号SF1234567890，联系人：张三。"

        loose_masked, _ = Shield(strategy="loose").mask(text)
        balanced_masked, _ = Shield(strategy="balanced").mask(text)
        strict_masked, _ = Shield(strategy="strict").mask(text)

        self.assertEqual(loose_masked, text)
        self.assertIn("<PERSON_1>", balanced_masked)
        self.assertIn("<ORDER_NO_1>", strict_masked)
        self.assertIn("<TRACKING_NO_1>", strict_masked)

    def test_alias_mode_preserves_session_consistency(self) -> None:
        shield = Shield(mode="alias", strategy="strict")
        first, _ = shield.mask("我是张三，收货地址：北京市朝阳区建国路88号。")
        second, _ = shield.mask("张三今天确认地址还是北京市朝阳区建国路88号。")

        self.assertNotIn("张三", first)
        self.assertNotIn("北京市朝阳区建国路88号", first)
        alias_name = first.split("，")[0].replace("我是", "")
        self.assertIn(alias_name, second)
        self.assertEqual(shield.unmask(second), "张三今天确认地址还是北京市朝阳区建国路88号。")

    def test_session_can_be_saved_and_loaded(self) -> None:
        shield = Shield(mode="alias", strategy="balanced")
        shield.mask("联系人：王小明，手机号13812345678。")

        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "session.json"
            shield.save_session(str(session_path))

            restored = Shield(mode="alias", strategy="balanced")
            restored.load_session(str(session_path))
            masked, _ = restored.mask("请再次联系王小明，手机号13812345678。")
            self.assertEqual(
                masked,
                shield.mask("请再次联系王小明，手机号13812345678。")[0],
            )

    def test_explicit_session_object_can_be_shared(self) -> None:
        session = ShieldSession()
        shield = Shield(mode="placeholder", strategy="balanced")

        first, _ = shield.mask("联系人：李四。", session=session)
        second, _ = shield.mask("请转告李四。", session=session)

        self.assertIn("<PERSON_1>", first)
        self.assertIn("<PERSON_1>", second)


if __name__ == "__main__":
    unittest.main()
