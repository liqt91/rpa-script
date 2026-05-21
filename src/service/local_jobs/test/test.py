import time
import random
from DrissionPage import ChromiumPage, ChromiumOptions

# 设置浏览器路径和用户数据目录
chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
user_data_path = r'D:\Chrome_Work'

co = ChromiumOptions()
co.set_browser_path(chrome_path)
co.set_user_data_path(user_data_path)
co.set_argument('--no-sandbox')
co.set_argument('--disable-blink-features=AutomationControlled')

# 启动 ChromiumPage
tab = ChromiumPage(addr_or_opts=co)

def random_sleep():
    """随机延迟模拟人类操作"""
    time.sleep(random.uniform(0.5, 1.5))

try:
    # 步骤 1：打开网页
    print("打开网页: xiaohongshu.com")
    tab.get('https://xiaohongshu.com')
    random_sleep()

    # 步骤 2：点击元素
    print("点击 「点击元素」(@name=hp-inputsearch-input)")
    element = tab.ele('@name=hp-inputsearch-input')
    element.click()
    random_sleep()

    # 步骤 3：在输入框中输入文本
    print("在 「输入文本」(#search-input) 中输入: 东方财富")
    input_box = tab.ele('#search-input')
    input_box.input('东方财富')
    random_sleep()

    # 步骤 4：点击搜索按钮
    print("点击 「点击元素」(css:#global > div.header-container:nth-of-type(1) > header.mask-paper:nth-of-type(1) > div.input-box:nth-of-type(1) > div.input-button:nth-of-type(1) > div.search-icon:nth-of-type(4))")
    search_button = tab.ele('css:#global > div.header-container:nth-of-type(1) > header.mask-paper:nth-of-type(1) > div.input-box:nth-of-type(1) > div.input-button:nth-of-type(1) > div.search-icon:nth-of-type(4)')
    search_button.click()
    random_sleep()


except Exception as e:
    print(f"操作过程中出现错误: {e}")

# 此脚本不会关闭浏览器，让用户能够继续观察页面