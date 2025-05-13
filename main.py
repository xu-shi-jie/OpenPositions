import datetime
import re
import sqlite3
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.google.com/",
}

def fetch_announcements():
    home_url = r'https://www.gaoxiaojob.com/daily/detail/{}.html'

    if Path('announcements.csv').exists():
        df = pd.read_csv('announcements.csv')
        i = df['page'].max()
    else:
        i = 22
        df = pd.DataFrame(columns=['url', 'page'])

    while True:
        url = home_url.format(i)
        print("\rFetching page {}...".format(url), end='')
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            i += 1
            break

        content = response.text
        ann_url = re.findall(
            r'www\.gaoxiaojob\.com/announcement/detail/.+?\.html', content)
        for url in ann_url:
            url = 'http://' + url
            if url not in df['url'].values:
                # insert new row
                df.loc[len(df)] = [url, i]

        i += 1
        df.to_csv('announcements.csv', index=False)


def fetch_daily():
    home_url = r'https://www.gaoxiaojob.com/'
    content = requests.get(home_url, headers=headers).text
    daily_url = re.findall(r'href="(/daily/detail/.+?.html)"', content)
    df = pd.read_csv('announcements.csv')

    for url in (pbar := tqdm(daily_url, desc="Iterating daily news...")):
        url = 'https://www.gaoxiaojob.com' + url
        pbar.set_description(f"Fetching {url}...")
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            continue
        content = response.text
        ann_url = re.findall(
            r'www\.gaoxiaojob\.com/announcement/detail/.+?\.html', content)

        for _url in ann_url:
            _url = 'http://' + _url
            if _url not in df['url'].values:
                # insert new row
                df.loc[len(df)] = [_url, re.split(r'/.', url)[-2]]
        df.to_csv('announcements.csv', index=False)

    ################# write to sqlite3 database ##################
    db = sqlite3.connect('gaoxiaojob.db')
    cursor = db.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            title TEXT,
            publish_time TEXT,
            ddl_time TEXT
        )
    ''')
    db.commit()

    visited_urls = cursor.execute('SELECT url FROM announcements').fetchall()
    visited_urls = [url[0] for url in visited_urls]

    df = pd.read_csv('announcements.csv')

    if Path('expired.txt').exists():
        with open('expired.txt', 'r') as f:
            expired = f.read().split('\n')
    else:
        expired = []

    for url in (pbar := tqdm(df['url'])):
        if url in expired or url in visited_urls:
            continue

        pbar.set_description(f"Inserting {url}...")

        try:
            title, publish_time, ddl_time = extract_info(url)

            cursor.execute('''
                INSERT INTO announcements (url, title, publish_time, ddl_time)
                VALUES (?, ?, ?, ?)
            ''', (url, title, publish_time, ddl_time))
            db.commit()

        except Exception as e:
            print(f" Error: {e}")
            expired.append(url)

            with open('expired.txt', 'w') as f:
                f.write('\n'.join(expired))

    db.close()


def extract_info(url):
    content = requests.get(url, headers=headers).text
    title = re.findall(r'title="(.+?)"', content)[0]
    try:
        publish_time = re.findall(r'发布时间：(\d{4}\-\d{2}\-\d{2})', content)[0]
    except:
        publish_time = 'Invalid Time Format'
    try:
        ddl_time = re.findall(r'截止.+?：(\d{4}\-\d{2}\-\d{2})', content)[0]
    except:
        ddl_time = 'Invalid Time Format'

    return title, publish_time, ddl_time


if __name__ == '__main__':
    max_count = 200
    c9_keywords = [
        '清华', '北京大学', '复旦', '上海交通大学', '西安交通大学',
        '浙江大学',  '中国科学技术大学',  '南京大学', '哈工大', '哈尔滨工业大学',]
    # fetch_announcements()
    fetch_daily()

    ################## write latest 200 announcements to Markdown file ##################
    with open('README.md', 'w') as f:
        f.write('# 高校人才网最新公告\n\n')
        f.write(
            f'This is a compiled repository for 高校人才网. Last Update: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} UTC.\n')
        # anchor
        f.write(
            f'## [Latest 200 Announcements (C9 included)](#c9-news-list) | [Latest 200 Announcements (C9 excluded)](#news-lists-c9-excluded)\n\n')

        # search not c9 universities
        db = sqlite3.connect('gaoxiaojob.db')
        cursor = db.cursor()
        cursor.execute(
            'SELECT * FROM announcements WHERE ' +
            ' AND '.join(['title NOT LIKE ?' for _ in c9_keywords]),
            ['%' + k + '%' for k in c9_keywords])  # exclude c9 universities
        data = cursor.fetchall()
        db.close()
        data = sorted(data, key=lambda x: x[3], reverse=True)
        f.write('## News Lists (C9 excluded)\n\n|标题|发布时间|截止时间|\n|---|---|---|\n')
        for i, row in enumerate(data[:max_count]):
            _, url, title, publish_time, ddl_time = row
            if publish_time == 'Invalid Time Format':
                publish_time = ''
            if ddl_time == 'Invalid Time Format':
                ddl_time = ''

            f.write(
                f'|[{title.replace("|", ":")}]({url})|{publish_time}|{ddl_time}|\n')
        f.write('\n\n')

        f.write('## C9 News List\n\n|标题|发布时间|截止时间|\n|---|---|---|\n')
        db = sqlite3.connect('gaoxiaojob.db')
        cursor = db.cursor()
        cursor.execute(
            'SELECT * FROM announcements WHERE ' +
            ' OR '.join(['title LIKE ?' for _ in c9_keywords]),
            ['%' + k + '%' for k in c9_keywords])
        data = cursor.fetchall()
        db.close()
        data = sorted(data, key=lambda x: x[3], reverse=True)
        for i, row in enumerate(data[:max_count]):
            _, url, title, publish_time, ddl_time = row
            if publish_time == 'Invalid Time Format':
                publish_time = ''
            if ddl_time == 'Invalid Time Format':
                ddl_time = ''

            f.write(
                f'|[{title.replace("|", ":")}]({url})|{publish_time}|{ddl_time}|\n')
