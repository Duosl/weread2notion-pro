import hashlib
import json
import os
import re
from bs4 import BeautifulSoup

import logging
# 启用调试日志
logging.basicConfig(level=logging.DEBUG)

import requests
from requests.utils import cookiejar_from_dict
from retrying import retry
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

URL_WEREAD = "https://weread.qq.com/"
URL_WEREAD_NOTEBOOKS = "https://weread.qq.com/api/user/notebook"
URL_WEREAD_BOOK_INFO = "https://weread.qq.com/api/book/info"
URL_WEREAD_BOOKMARKLIST = "https://weread.qq.com/web/book/bookmarklist"
URL_WEREAD_CHAPTER_INFO = "https://weread.qq.com/web/book/chapterInfos"
URL_WEREAD_REVIEW_LIST = "https://weread.qq.com/web/review/list"
URL_WEREAD_READ_INFO = "https://weread.qq.com/web/book/getProgress"
URL_WEREAD_SHELF_SYNC = "https://weread.qq.com/web/shelf/syncBook"
URL_WEREAD_HISTORY = "https://weread.qq.com/api/readdata/summary?synckey=0"


class WeReadApi:
    def __init__(self):
        self.cookie = self.get_cookie()
        self.session = requests.Session()
        self.session.cookies = self.parse_cookie_string()
        self.session.headers.update({
            'Cookie': self.cookie,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        })

    def try_get_cloud_cookie(self, url, id, password):
        if url.endswith("/"):
            url = url[:-1]
        req_url = f"{url}/get/{id}"
        data = {"password": password}
        result = None
        response = requests.post(req_url, data=data)
        if response.status_code == 200:
            data = response.json()
            cookie_data = data.get("cookie_data")
            if cookie_data and "weread.qq.com" in cookie_data:
                cookies = cookie_data["weread.qq.com"]
                cookie_str = "; ".join(
                    [f"{cookie['name']}={cookie['value']}" for cookie in cookies]
                )
                result = cookie_str
        return result

    def get_cookie(self):
        url = os.getenv("CC_URL")
        if not url:
            url = "https://cookiecloud.malinkang.com/"
        id = os.getenv("CC_ID")
        password = os.getenv("CC_PASSWORD")
        cookie = os.getenv("WEREAD_COOKIE")
        if url and id and password:
            cookie = self.try_get_cloud_cookie(url, id, password)
        if not cookie or not cookie.strip():
            raise Exception("没有找到cookie，请按照文档填写cookie")
        return cookie

    def parse_cookie_string(self):
        cookies_dict = {}
        
        # 使用正则表达式解析 cookie 字符串
        pattern = re.compile(r'([^=]+)=([^;]+);?\s*')
        matches = pattern.findall(self.cookie)
        
        for key, value in matches:
            cookies_dict[key] = value.encode('unicode_escape').decode('ascii')
        # 直接使用 cookies_dict 创建 cookiejar
        cookiejar = cookiejar_from_dict(cookies_dict)
        
        return cookiejar

    def get_standard_headers(self):
        return {
            'Cookie': self.cookie,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Connection': 'keep-alive',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'upgrade-insecure-requests': '1'
        }

    def visit_homepage(self):
        """访问微信读书主页"""
        try:
            self.session.get(URL_WEREAD, headers=self.get_standard_headers(), timeout=30)
        except Exception as e:
            print("访问主页失败:", str(e))

    def _get_bookshelf_bookIds(self):
        """获取所有书架书籍 id"""
        self.visit_homepage()
        # 1. 模拟请求页面
        r = self.session.get("https://weread.qq.com/web/shelf")
        if r.ok:
            html_content = r.text
            # 2. 解析 HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            # 3. 查找所有 script 标签内容
            scripts = soup.find_all('script')
            # 4. 正则匹配 __INITIAL_STATE__
            pattern = re.compile(r'window\.__INITIAL_STATE__\s*=\s*({[\s\S]*?});')

            initial_state = None
            for script in scripts:
                if script.string and pattern.search(script.string):
                    match = pattern.search(script.string)
                    if match:
                        json_str = match.group(1)
                        # 5. 转换 JSON 字符串为 Python 字典
                        try:
                            initial_state = json.loads(json_str)
                            print("✅ 成功提取 __INITIAL_STATE__")
                            rawBooks = initial_state['shelf']['rawBooks']
                            bookIds = [item["bookId"] for item in rawBooks]
                            return bookIds
                        except json.JSONDecodeError as e:
                            print("❌ JSON 解析失败：", e)
                        break

            if not initial_state:
                print("❌ 没有找到 __INITIAL_STATE__")
        else:
            errcode = r.json().get("errcode",0)
            self.handle_errcode(errcode)
            raise Exception(f"Could not get bookshelf {r.text}")

    def get_bookshelf(self):
        """获取所有书架书籍信息"""
        self.visit_homepage()
        bookIds = api.get_bookshelf_bookIds()
        r = self.session.post(URL_WEREAD_SHELF_SYNC, json={"bookIds": bookIds})
        if r.ok:
            return r.json()
        else:
            errcode = r.json().get("errcode",0)
            self.handle_errcode(errcode)
            raise Exception(f"Could not get bookshelf {r.text}")
        
    def handle_errcode(self,errcode):
        if( errcode== -2012 or errcode==-2010):
            print(f"::error::微信读书Cookie过期了，请参考文档重新设置。https://mp.weixin.qq.com/s/B_mqLUZv7M1rmXRsMlBf7A")

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_notebooklist(self):
        """获取笔记本列表"""
        self.visit_homepage()
        r = self.session.get(URL_WEREAD_NOTEBOOKS)
        if r.ok:
            data = r.json()
            books = data.get("books")
            books.sort(key=lambda x: x["sort"])
            return books
        else:
            errcode = r.json().get("errcode",0)
            self.handle_errcode(errcode)
            raise Exception(f"Could not get notebook list {r.text}")

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_bookinfo(self, bookId):
        """获取书的详情"""
        self.visit_homepage()
        params = dict(bookId=bookId)
        r = self.session.get(URL_WEREAD_BOOK_INFO, params=params)
        if r.ok:
            return r.json()
        else:
            errcode = r.json().get("errcode",0)
            self.handle_errcode(errcode)
            print(f"Could not get book info {r.text}")


    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_bookmark_list(self, bookId):
        """获取书的书签列表"""
        self.visit_homepage()
        params = dict(bookId=bookId)
        r = self.session.get(URL_WEREAD_BOOKMARKLIST, params=params)
        if r.ok:
            with open("bookmark.json","w") as f:
                f.write(json.dumps(r.json(),indent=4,ensure_ascii=False))
            bookmarks = r.json().get("updated")
            return bookmarks
        else:
            errcode = r.json().get("errcode",0)
            self.handle_errcode(errcode)
            raise Exception(f"Could not get {bookId} bookmark list")

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_read_info(self, bookId):
        self.visit_homepage()
        params = dict(
            noteCount=1,
            readingDetail=1,
            finishedBookIndex=1,
            readingBookCount=1,
            readingBookIndex=1,
            finishedBookCount=1,
            bookId=bookId,
            finishedDate=1,
        )
        headers = {
            "baseapi":"32",
            "appver":"8.2.5.10163885",
            "basever":"8.2.5.10163885",
            "osver":"12",
            "User-Agent": "WeRead/8.2.5 WRBrand/xiaomi Dalvik/2.1.0 (Linux; U; Android 12; Redmi Note 7 Pro Build/SQ3A.220705.004)",
        }
        r = self.session.get(URL_WEREAD_READ_INFO,headers=headers, params=params)
        if r.ok:
            return r.json()
        else:
            errcode = r.json().get("errcode",0)
            self.handle_errcode(errcode)
            raise Exception(f"get {bookId} read info failed {r.text}")

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_review_list(self, bookId):
        self.visit_homepage()
        params = dict(bookId=bookId, listType=11, mine=1, syncKey=0)
        r = self.session.get(URL_WEREAD_REVIEW_LIST, params=params)
        if r.ok:
            reviews = r.json().get("reviews", [])
            reviews = list(map(lambda x: x.get("review"), reviews))
            reviews = [
                {"chapterUid": 1000000, **x} if x.get("type") == 4 else x
                for x in reviews
            ]
            return reviews
        else:
            errcode = r.json().get("errcode",0)
            self.handle_errcode(errcode)
            raise Exception(f"get {bookId} review list failed {r.text}")



    
    def get_api_data(self):
        self.visit_homepage()
        r = self.session.get(URL_WEREAD_HISTORY)
        print(r.text)
        if r.ok:
            return r.json()
        else:
            errcode = r.json().get("errcode",0)
            self.handle_errcode(errcode)
            raise Exception(f"get history data failed {r.text}")

    

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_chapter_info(self, bookId):
        self.visit_homepage()
        body = {"bookIds": [str(bookId)], "synckeys": [0], "teenmode": 0}
        headers = {
            'Cookie': self.cookie,
            'Content-Type': 'application/json;charset=UTF-8',
            'Accept': 'application/json, text/plain, */*',

        }
        r = self.session.post(URL_WEREAD_CHAPTER_INFO, headers=headers, json=body)
        if (
            r.ok
            and "data" in r.json()
            and len(r.json()["data"]) == 1
            and "updated" in r.json()["data"][0]
        ):
            update = r.json()["data"][0]["updated"]
            update.append(
                {
                    "chapterUid": 1000000,
                    "chapterIdx": 1000000,
                    "updateTime": 1683825006,
                    "readAhead": 0,
                    "title": "点评",
                    "level": 1,
                }
            )
            return {item["chapterUid"]: item for item in update}
        else:
            raise Exception(f"get {bookId} chapter info failed {r.text}")

    def transform_id(self, book_id):
        id_length = len(book_id)
        if re.match("^\\d*$", book_id):
            ary = []
            for i in range(0, id_length, 9):
                ary.append(format(int(book_id[i : min(i + 9, id_length)]), "x"))
            return "3", ary

        result = ""
        for i in range(id_length):
            result += format(ord(book_id[i]), "x")
        return "4", [result]

    def calculate_book_str_id(self, book_id):
        md5 = hashlib.md5()
        md5.update(book_id.encode("utf-8"))
        digest = md5.hexdigest()
        result = digest[0:3]
        code, transformed_ids = self.transform_id(book_id)
        result += code + "2" + digest[-2:]

        for i in range(len(transformed_ids)):
            hex_length_str = format(len(transformed_ids[i]), "x")
            if len(hex_length_str) == 1:
                hex_length_str = "0" + hex_length_str

            result += hex_length_str + transformed_ids[i]

            if i < len(transformed_ids) - 1:
                result += "g"

        if len(result) < 20:
            result += digest[0 : 20 - len(result)]

        md5 = hashlib.md5()
        md5.update(result.encode("utf-8"))
        result += md5.hexdigest()[0:3]
        return result

    def get_url(self, book_id):
        return f"https://weread.qq.com/web/reader/{self.calculate_book_str_id(book_id)}"
