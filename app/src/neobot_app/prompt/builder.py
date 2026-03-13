import time
from datetime import date,datetime
from lunarcalendar import Converter, Solar, Lunar
from neobot_app.config.instance import  BotConfig
from neobot_adapter.model import *
from typing import Optional



basic_prompt = """
<当前时间>{current_time}</当前时间>
<群聊>{group_name}[群号:{group_id}]{group_description}</群聊>
<聊天记录>
{message_list}
</聊天记录>
<群友信息>
{member_list}
</群友信息>
<你是谁>
你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.
{bot_data},现在你在这个群里聊天,你打算用日常,口语化的方式回复最后几句聊天记录里你比较感兴趣的内容,个性化一些,不用特意突出科学背景,聊天时你一般不会使用冒号,括号,句号也一般不使用,而是直接换行分成多条.一次回复一句即可,不要超过三小句.
</你是谁>
<你的印象>
{key_word_reaction_list}
你想起来之前:
{memory_list}
这些内容都是之前的内容,可能很久之前,也可能只是不久之前.
</你的印象>
"""

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

async def get_group_chat_prompt(group_id: int,message_list: str,member_list : str,key_world_message : str,memory_list : str) -> str:
    """
    获取提示词

    Returns:
        str: 提示词
    """
    current_time = get_current_time_and_lunar_date()
    group_description = BotConfig.chat.group_description
    alias_list = BotConfig.bot.alias_name
    valid_aliases = [alias.strip() for alias in alias_list if alias.strip()]
    other_name = ""
    if valid_aliases:
        other_name = "、".join(valid_aliases)
        other_name = ",也有人叫你" + other_name
    return basic_prompt.format(
        current_time=current_time,
        group_id=group_id,
        group_description=group_description,
        message_list=message_list,
        member_list=member_list,
        bot_name=BotConfig.bot.nick_name,
        bot_account=BotConfig.bot.account,
        other_name=other_name,
        bot_data=BotConfig.bot.bot_data,
        key_word_reaction_list=key_world_message,
        memory_list=memory_list,

    )
