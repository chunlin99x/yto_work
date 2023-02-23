# -*- coding:utf-8 -*-
'''===================================================
@Author : Mr. chunlin
@Time   : 2023-02-22 17:42
@Desc   : 
==================================================='''
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
import tornado
import os
import json
from uuid import uuid4
from sftp import SFTP
import requests
import tornado.web
from tornado.concurrent import run_on_executor
from urllib.parse import quote
import math

from settings import  XC_URL,XC_PASSPORT


class XCApiEnsemble(object):
    @staticmethod
    def get_account(ip,account):
        # 根据传入的发布账号 获取到密码
        login_data = {'username': 'admin', 'password': XC_PASSPORT, "develop_key": "xc"}
        login_url = '{}/prod-api/user/login'.format(XC_URL)
        with requests.session() as req_session:
            req_session.post(url=login_url, json=login_data)
            url = f"{XC_URL}/prod-api/cmdb/get_number_list?page=1&limit=20&account_name={account}&ip={ip}"
            with req_session.get(url=url) as response:
                result = response.json()
                info = result["results"]
                if info:
                    user = info[0]["account_name"]
                    password = info[0]["pwd"]
                    return {
                        "user": user,
                        "pwd": password
                    }
        return None


class FileUploadHandler(tornado.web.RequestHandler):
    '''''通过线程池来实现异步（使用requests模块）'''
    executor = ThreadPoolExecutor(10)

    @run_on_executor
    def write_file(self):
        file_path = None
        ret = {}
        try:
            upload_path = os.path.join(os.path.dirname(__file__), 'files')  # 文件的暂存路径
            file_metas = self.request.files.get('file')  # 提取表单中‘name'为‘file'的文件元数据
            for meta in file_metas:
                filename = meta['filename']
                uuid_folder = os.path.join(upload_path, str(uuid4()))
                file_path = os.path.join(upload_path, uuid_folder,filename)
                if not os.path.exists(uuid_folder):
                    os.makedirs(uuid_folder, exist_ok=True)
                with open(file_path, 'wb') as up:
                    up.write(meta['body'])
            host = self.get_argument('host')
            username = self.get_argument('username')
            port = 22
            if not all([host,username]):
                raise tornado.web.HTTPError(400, str("参数错误:host,username"))

            reps = XCApiEnsemble.get_account(host,username)
            if not reps:
                raise tornado.web.HTTPError(400, str("密码不存在"))
            sftp_client = SFTP(host, port, username, password=reps["pwd"])
            to_path = self.get_argument('path')
            has_exception = sftp_client.upload_file(file_path, to_path)
            if has_exception:
                raise has_exception
        except Exception  as  e:
            ret["code"] = 1
            ret["error"] = f"上传失败:{str(e)}"
        else:
            # 调用sftp
            ret["code"] = 0
            ret["error"] = f"上传成功."

        return  ret

    @tornado.gen.coroutine  # 协程装饰器
    def post(self):
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        host = self.get_argument('host')
        username = self.get_argument('username')
        path = self.get_argument('path')
        if not all([host, username,path]):
            self.write(json.dumps({"code":1,"error":"参数错误host,username,path"}))
            return


        response = yield self.write_file()
        self.write(json.dumps(response))


class FileDownloadHandler(tornado.web.RequestHandler):

    def get(self,file_path):

        ret = {}

        try:
            host = self.get_argument('host')
            username = self.get_argument('username')
            if not all([host, username]):
                self.write(json.dumps({"code": 1, "error": "参数错误host,username"}))
                return

            reps = XCApiEnsemble.get_account(host, username)
            if not reps:
                self.write(json.dumps({"code": 1, "error": "cmdb中不存在密码"}))
                return
            file_path =  os.path.join("/",file_path)
            sftp_client = SFTP(host, 22, username, password=reps["pwd"])
            filename =  os.path.basename(file_path)
            upload_path = os.path.join(os.path.dirname(__file__), 'files')  # 文件的暂存路径
            uuid_folder = os.path.join(upload_path, str(uuid4()))
            local_file_path = os.path.join(upload_path, uuid_folder, filename)
            if not os.path.exists(uuid_folder):
                os.makedirs(uuid_folder, exist_ok=True)

            has_exception = sftp_client.get_file(file_path,local_file_path)
            if has_exception:
                raise has_exception
                return


            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header('Content-Disposition',
                                    'attachment;filename="{filename}"'.format(filename=quote(filename)))
            with open(local_file_path, 'rb') as f:
                self.write(f.read())
            self.finish()

        except Exception as e:
                ret["code"] = 1
                ret["error"] = f"下载失败:{str(e)}"
                self.write(json.dumps(ret))




class FileListHandler(tornado.web.RequestHandler):

    def get(self):
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        ret = {}
        try:
            host = self.get_argument('host')
            username = self.get_argument('username')
            path = self.get_argument('path',"/")

            if not all([host, username,path]):
                self.write(json.dumps({"code": 1, "error": "参数错误host,username,path"}))
                return
            if path.endswith("../") :
                path = os.path.dirname(path[:-4])

            reps = XCApiEnsemble.get_account(host, username)
            if not reps:
                self.write(json.dumps({"code": 1, "error": "cmdb中不存在密码"}))
                return
            sftp_client = SFTP(host, 22, username, password=reps["pwd"])
            file_attr_list = sftp_client.sftp.listdir_attr(path)
            file_list = []
            keys = ["mod","file_count","group","owner","size","m","d","time","filename"]
            for i in file_attr_list:
                attr = i.longname.split(' ')
                attr = [i for i in attr if i != ""]
                attr_dict =dict(zip(keys,attr))
                attr_dict['size'] = math.floor(int(attr_dict['size']) / 1024)
                attr_dict["is_dir"] = True if attr_dict['mod'].startswith("d") else False
                file_list.append(attr_dict)
            ret["data"]= {
                "files":file_list,
                "path":path,
            }

        except Exception as e:
            ret["code"] = 1
            ret["error"] = f"获取失败:{str(e)}"
            self.write(json.dumps(ret))
            return

        else:
            ret["code"] = 0
            self.write(json.dumps(ret))


class FolderCreateHandler(tornado.web.RequestHandler):

    def  get(self):
        ret = {}
        try:
            host = self.get_argument('host')
            username = self.get_argument('username')
            path = self.get_argument('path', "/")
            folder = self.get_argument('folder')

            if not all([host, username, path,folder]):
                self.write(json.dumps({"code": 1, "error": "参数错误host,username,path"}))
                return
            reps = XCApiEnsemble.get_account(host, username)
            if not reps:
                self.write(json.dumps({"code": 1, "error": "cmdb中不存在密码"}))
                return
            sftp_client = SFTP(host, 22, username, password=reps["pwd"])
            full = path+"/"+folder
            sftp_client.sftp.mkdir(full)
        except Exception as e:
            ret["code"] = 1
            ret["error"] = f"创建失败:{str(e)}"
            self.write(json.dumps(ret))
            return

        else:
            ret["code"] = 0
            self.write(json.dumps(ret))




