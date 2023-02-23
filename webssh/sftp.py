# -*- coding: utf-8 -*-
"""
-------------------------------------------------
   File Name：      sftp
   Description:
   Author:          Administrator
   date：           2018-10-25
-------------------------------------------------
   Change Activity:
                    2018-10-25:
-------------------------------------------------
"""
import os
import logging
import paramiko
import tornado.web


class SFTP:
    def __init__(self, host, port, username, password=None, key_file=None):
        self.host = host
        self.password = password
        self.username = username
        self.transport = paramiko.Transport(sock="{}:{}".format(host, port))
        self.ssh = paramiko.SSHClient()

        if key_file:
            private_key = paramiko.RSAKey.from_private_key_file(key_file)
            self.transport.connect(username=self.username, pkey=private_key)
        else:
            self.transport.connect(username=self.username, password=password)

        self.sftp = paramiko.SFTPClient.from_transport(self.transport)

    def put_file(self, local_file, user_home):
        """
        user_home指用户的家目录，比如：/home/zz，主要用于获取用户的uid和gid
        :param local_file: 本地文件的路径
        :param user_home: 远程服务器登录用户的家目录，路径最后没有"/"
        """
        try:
            filename = os.path.basename(local_file)
            remote_file = '{}/{}'.format(user_home, filename)
            self.sftp.put(local_file, remote_file)
            file_stat = self.sftp.stat(user_home)
            self.sftp.chown(remote_file, file_stat.st_uid, file_stat.st_gid)
        except Exception as e:
            return e
            logging.getLogger().error(e)
        finally:
            self.transport.close()

    def get_file(self, remote_file, local_file):
        try:
            self.sftp.get(remote_file, local_file)
        except Exception as e:
            return e
            logging.getLogger().error(e)
        finally:
            self.transport.close()


    def upload_file(self, local_path, remote_path):
        return  self.put_file(local_path, remote_path)



    def connect(self):
        # 建立登录连接
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(hostname=self.host, port=22, username=self.username, password=self.password,compress=True)

    def execute_cmd(self, cmd):
        self.connect()
        stdin, stdout, stderr = self.ssh.exec_command(cmd)
        res, err = stdout.read(), stderr.read()
        result = res if res else err
        return result.decode()


