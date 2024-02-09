import datetime
import re
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import requests
from tqdm import tqdm


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
        response = requests.get(url)
        if response.status_code != 200:
            i += 1
            break

        content = response.text
        ann_url = re.findall(r'www\.gaoxiaojob\.com/announcement/detail/.+?\.html', content)
        for url in ann_url:
            url = 'http://' + url
            if url not in df['url'].values:
                # insert new row
                df.loc[len(df)] = [url, i]

        i += 1
        df.to_csv('announcements.csv', index=False)


def fetch_daily():
    home_url = r'https://www.gaoxiaojob.com/'
    content = requests.get(home_url).text
    daily_url = re.findall(r'href="(/daily/detail/.+?.html)"', content)
    df = pd.read_csv('announcements.csv')

    for url in (pbar:=tqdm(daily_url)):
        url = 'https://www.gaoxiaojob.com' + url
        pbar.set_description(f"Fetching {url}...")
        response = requests.get(url)
        if response.status_code != 200:
            continue
        content = response.text
        ann_url = re.findall(r'www\.gaoxiaojob\.com/announcement/detail/.+?\.html', content)
        
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


    for url in (pbar:=tqdm(df['url'])):
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
    content = requests.get(url).text
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
    # fetch_announcements()
    fetch_daily()
    ################## write latest 200 announcements to Markdown file ##################
    with open('README.md', 'w') as f:
        f.write('# 高校人才网最新公告\n\n')
        f.write(f'This is a repository for 高校人才网. Last Update: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} UTC.\n')
        db = sqlite3.connect('gaoxiaojob.db')
        cursor = db.cursor()
        cursor.execute('''
            SELECT * FROM announcements ORDER BY publish_time DESC LIMIT 300
        ''')
        data = cursor.fetchall()
        db.close()
        f.write('## News List\n\n|标题|发布时间|截止时间|\n|---|---|---|\n')
        for i, row in enumerate(data):
            _, url, title, publish_time, ddl_time = row
            if publish_time == 'Invalid Time Format':
                publish_time = ''
            if ddl_time == 'Invalid Time Format':
                ddl_time = ''

            f.write(f'|[{title.replace("|", ":")}]({url})|{publish_time}|{ddl_time}|\n')
        f.write('\n\n')
    