# 以下是为该项目编写的 GitHub 项目说明文档：
智能室内消防报警系统
项目概述
本项目是一个智能室内消防报警系统，结合了串口通信、视频监控、传感器数据采集与分析、数据库记录以及 OneNet 平台数据上报等功能。系统通过传感器实时监测室内环境数据，如温度、湿度、光照、人体红外和烟雾等，当数据超过预设阈值时，可自动控制消防水闸开启。同时，系统还具备视频监控功能，能够实时检测室内人流量，并将相关数据记录到本地数据库，同时上报至 OneNet 平台。此外，项目还提供了一个基于 Flask 的 Web 界面，用于展示系统的实时数据和历史记录。
功能特性
传感器数据采集：通过串口通信获取传感器数据，包括温度、湿度、光照、人体红外和烟雾等。
阈值报警：当传感器数据超过预设阈值时，自动控制消防水闸开启。
视频监控与人流量检测：利用 YOLOv8 模型实时检测室内人流量，并在界面上显示。
数据记录：将传感器数据、水闸操作记录和用户操作记录保存到本地 SQLite 数据库。
数据上报：将传感器数据和人流量数据上报至 OneNet 平台。
Web 界面展示：提供一个基于 Flask 的 Web 界面，展示系统的实时数据和历史记录。
项目结构
plaintext
.
├── PAPT.py             # 主程序文件
├── OnenetConnect.py    # OneNet 平台连接模块
├── smart_monitor.db    # 本地 SQLite 数据库文件
└── ...                 # 其他可能的依赖文件
安装与配置
环境要求
Python 3.x
相关 Python 库：tkinter, Pillow, opencv-python, numpy, pyserial, ultralytics, flask, sqlite3
安装依赖
bash
pip install pillow opencv-python numpy pyserial ultralytics flask
OneNet 平台配置
在 PAPT.py 文件中，修改 ONENET_CONFIG 字典，配置 OneNet 平台的产品 ID、设备名称和 token：
python
运行
ONENET_CONFIG = {
    "product_id": "your_product_id",
    "device_name": "your_device_name",
    "headers": {
        "Content-Type": "application/json",
        "token": "your_token"
    }
}
使用方法
运行主程序
bash
python PAPT.py
界面操作
串口设置：选择可用的串口和波特率，点击 “打开串口” 按钮开启串口通信。
传感器数据：在界面上查看实时传感器数据，点击 “上报数据” 按钮手动上报数据。
阈值设置：设置温度、湿度和光照的阈值。
消防水闸控制：选择控制模式（自动或手动），手动控制水闸开关。
视频监控：点击 “开始监控” 按钮启动视频监控，点击 “停止监控” 按钮停止监控，点击 “拍照” 按钮拍摄快照。
数据查看：点击 “查看历史数据” 按钮，查看传感器数据、水闸操作记录和用户操作记录。
Web 界面访问
在浏览器中访问 http://127.0.0.1:5000，即可查看系统的实时数据和历史记录。
代码说明
主程序文件 PAPT.py
类 SmartMonitorSystem：系统的核心类，负责初始化界面、设备和数据库，处理串口数据、视频监控和水闸控制等功能。
Flask 应用：提供 Web 界面的路由和数据接口。
OneNet 连接模块 OnenetConnect.py
负责与 OneNet 平台进行数据通信，实现设备属性的上报功能。
注意事项
确保串口设备正常连接，并且串口参数设置正确。
确保 OneNet 平台的配置信息正确，否则数据上报可能会失败。
视频监控功能依赖于摄像头设备，请确保摄像头正常工作。
贡献与反馈
如果你对本项目有任何建议或发现了问题，请在 GitHub 上提交 Issue 或 Pull Request。
许可证
本项目采用 MIT 许可证。
