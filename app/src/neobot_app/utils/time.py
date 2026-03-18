import time
from datetime import date,datetime
from lunarcalendar import Converter, Solar, Lunar

class LunarStr:
    months = ["正月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"]
    days = ["初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
            "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
            "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]

    @classmethod
    def from_year_month_day(cls, year, month, day):
        solar = Solar(year, month, day)
        lunar = Converter.Solar2Lunar(solar)
        return cls(lunar)

    def __repr__(self):
        return f"LunarStr(year={self.year}, month={self.month}, day={self.day})"

    def __init__(self, lunar):
        self.year = lunar.year
        self.month = lunar.month
        self.day = lunar.day
        try:
            self.month_str = self.months[lunar.month - 1]
            self.day_str = self.days[lunar.day - 1]
        except IndexError:
            raise ValueError("月份或日期超出有效范围！")
        if lunar.isleap:
            self.month_str = "闰" + self.month_str

    def get_calendar_date_str(self):
        if self.day == 1:
            return self.month_str
        else:
            return self.day_str

    def get_date_str(self):
        return self.month_str + self.day_str


def get_current_time_and_lunar_date() -> str:
    """
    获取当前时间和农历日期

    Returns:
        str: 格式化的当前时间和农历日期信息
    """
    # 获取当前时间
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    week = week_list[datetime.today().weekday()]

    # 使用date.today()获取当前日期并转换为农历
    today = date.today()
    solar = Solar.from_date(today)
    lunar = Converter.Solar2Lunar(solar)
    lunar_time = LunarStr(lunar).get_date_str()
    return f"现在的时间是{current_time},{week}.农历日期是{lunar_time}"