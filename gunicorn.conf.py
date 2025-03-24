# -*- coding: utf-8 -*-
"""gunicorn.conf

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1LWi4TriIqvSBrCaodSDyuSCGu3yfvCrH
"""
# gunicorn.conf.py
bind = "0.0.0.0:10000"
workers = 5  # ← 以前より増やす
loglevel = "debug"
accesslog = "-"
errorlog = "-"
timeout = 120
reload = True  # ← 追加
