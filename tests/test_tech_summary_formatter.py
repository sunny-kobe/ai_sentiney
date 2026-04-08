from src.utils.tech_summary_formatter import format_tech_summary_for_display


def test_format_tech_summary_for_display_converts_structured_tags_to_plain_chinese():
    raw = (
        "[日线_MACD_空头-超弱_无背驰_0] "
        "[日线_OBV_资金流出_0] "
        "[日线_KDJ_中性_0] "
        "[日线_RSI_中性_42.0_0] "
        "[日线_ATR_正常波动_0] "
        "[日线_布林带_下半区_0] "
        "[日线_量能_平量_量比1.17x_0]"
    )

    formatted = format_tech_summary_for_display(raw)

    assert formatted == (
        "MACD空头-超弱，无背驰；"
        "OBV资金流出；"
        "KDJ中性；"
        "RSI 42.0，中性；"
        "ATR正常波动；"
        "布林带下半区；"
        "量能平量，量比1.17x"
    )


def test_format_tech_summary_for_display_keeps_plain_text_unchanged():
    raw = "MACD金叉，站上20日线"

    assert format_tech_summary_for_display(raw) == raw
