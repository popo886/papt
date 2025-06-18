import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from PIL import Image, ImageTk
import cv2
import numpy as np
import serial
import serial.tools.list_ports
import threading
import binascii
import sys
import time
import logging
from pathlib import Path
from ultralytics import YOLO
import OnenetConnect
import sqlite3
from datetime import datetime
from flask import Flask, jsonify

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 创建Flask应用
app = Flask(__name__)

# 加载预训练的 YOLOv8 模型
model1 = YOLO("yolov8n.pt")

# OneNet平台配置
ONENET_CONFIG = {
    "product_id": "74gffow34P",
    "device_name": "httpdevice1",
    "headers": {
        "Content-Type": "application/json",
        "token": "version=2018-10-31&res=products%2F74gffow34P%2Fdevices%2Fhttpdevice1&et=1810090102&method=md5&sign=BuMez32GB3yBMr61os%2BVRA%3D%3D"
    }
}

# 串口配置
BAUDRATES = (1200, 2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200)
BYTESIZES = (5, 6, 7, 8)
PARITIES = {'None': 'N', 'Even': 'E', 'Odd': 'O', 'Mark': 'M', 'Space': 'S'}
STOPBITS = (1, 1.5, 2)
TIMEOUT = 0.015

class SmartMonitorSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("智能室内消防报警系统")
        self.root.geometry("1200x900")
        
        # 初始化数据库
        self.init_database()
        
        # 初始化变量
        self.init_variables()
        
        # 创建界面
        self.create_gui()
        
        # 初始化串口和视频捕获
        self.init_devices()

    def init_database(self):
        """初始化数据库"""
        self.conn = sqlite3.connect('smart_monitor.db')
        cursor = self.conn.cursor()
        
        # 创建传感器数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                temperature REAL,
                humidity REAL,
                light REAL,
                pir INTEGER,
                gas INTEGER
            )
        ''')
        
        # 创建水闸操作记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS valve_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                operation TEXT,
                mode TEXT,
                operator TEXT
            )
        ''')
        
        # 创建用户操作记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                operation TEXT,
                details TEXT
            )
        ''')
        
        self.conn.commit()

    def init_variables(self):
        # 串口相关
        self.portisopen = False
        self.TX = 0
        self.RX = 0
        
        # 视频相关
        self.is_capturing = False
        self.is_video_mode = False
        self.snapshot_count = 0
        
        # 阈值设置
        self.temp_threshold = tk.DoubleVar(value=30.0)
        self.humi_threshold = tk.DoubleVar(value=80.0)
        self.light_threshold = tk.DoubleVar(value=1000.0)
        
        # 消防水闸状态
        self.valve_state = tk.BooleanVar(value=False)
        self.valve_mode = tk.StringVar(value="自动")  # 自动/手动控制模式
        
        # 传感器数据
        self.sensor_data = {
            'temp': tk.StringVar(value="0.0"),
            'humi': tk.StringVar(value="0.0"),
            'light': tk.StringVar(value="0.0"),
            'pir': tk.StringVar(value="0"),
            'gas': tk.StringVar(value="0")
        }

        # 添加串口数据缓冲
        self.serial_buffer = ""
        
        # 添加串口接收线程
        self.serial_thread = None
        self.is_receiving = False

    def create_gui(self):
        # 创建主框架
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左侧控制面板
        control_panel = tk.LabelFrame(main_frame, text="控制面板")
        control_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)
        
        # 串口设置区域
        self.create_serial_settings(control_panel)
        
        # 传感器数据输入区域
        self.create_sensor_inputs(control_panel)
        
        # 阈值设置区域
        self.create_threshold_settings(control_panel)
        
        # 消防水闸控制区域
        self.create_relay_control(control_panel)
        
        # 数据记录查看按钮
        self.create_data_view_button(control_panel)
        
        # 右侧视频监控区域
        video_panel = tk.LabelFrame(main_frame, text="视频监控")
        video_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.create_video_panel(video_panel)

    def create_serial_settings(self, parent):
        serial_frame = tk.LabelFrame(parent, text="串口设置")
        serial_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 端口选择
        ports = self.get_available_ports()
        self.port_var = tk.StringVar(value=ports[0] if ports else "")
        tk.Label(serial_frame, text="端口:").pack(side=tk.LEFT)
        tk.OptionMenu(serial_frame, self.port_var, *ports).pack(side=tk.LEFT)
        
        # 波特率选择
        self.baud_var = tk.StringVar(value="9600")
        tk.Label(serial_frame, text="波特率:").pack(side=tk.LEFT)
        tk.OptionMenu(serial_frame, self.baud_var, *BAUDRATES).pack(side=tk.LEFT)
        
        # 打开/关闭串口按钮
        self.serial_btn = tk.Button(serial_frame, text="打开串口", command=self.toggle_serial)
        self.serial_btn.pack(side=tk.LEFT, padx=5)

    def create_sensor_inputs(self, parent):
        sensor_frame = tk.LabelFrame(parent, text="传感器数据")
        sensor_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 创建传感器输入框
        sensors = [
            ("温度", "temp", "℃"),
            ("湿度", "humi", "%"),
            ("光照", "light", "lux"),
            ("人体红外", "pir", ""),
            ("烟雾", "gas", "")
        ]
        
        for label, key, unit in sensors:
            frame = tk.Frame(sensor_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)
            
            tk.Label(frame, text=f"{label}:").pack(side=tk.LEFT)
            tk.Entry(frame, textvariable=self.sensor_data[key], width=10).pack(side=tk.LEFT)
            if unit:
                tk.Label(frame, text=unit).pack(side=tk.LEFT)

        # 上报按钮
        tk.Button(sensor_frame, text="上报数据", command=self.report_sensor_data).pack(pady=5)

    def create_threshold_settings(self, parent):
        threshold_frame = tk.LabelFrame(parent, text="阈值设置")
        threshold_frame.pack(fill=tk.X, padx=5, pady=5)
        
        thresholds = [
            ("温度阈值", self.temp_threshold, "℃"),
            ("湿度阈值", self.humi_threshold, "%"),
            ("光照阈值", self.light_threshold, "lux")
        ]
        
        for label, var, unit in thresholds:
            frame = tk.Frame(threshold_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)
            
            tk.Label(frame, text=f"{label}:").pack(side=tk.LEFT)
            tk.Entry(frame, textvariable=var, width=10).pack(side=tk.LEFT)
            tk.Label(frame, text=unit).pack(side=tk.LEFT)

    def create_relay_control(self, parent):
        valve_frame = tk.LabelFrame(parent, text="消防水闸控制")
        valve_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 控制模式选择
        mode_frame = tk.Frame(valve_frame)
        mode_frame.pack(fill=tk.X, padx=5, pady=2)
        
        tk.Label(mode_frame, text="控制模式:").pack(side=tk.LEFT)
        tk.Radiobutton(mode_frame, text="自动", variable=self.valve_mode, 
                      value="自动").pack(side=tk.LEFT)
        tk.Radiobutton(mode_frame, text="手动", variable=self.valve_mode, 
                      value="手动").pack(side=tk.LEFT)
        
        # 水闸开关控制
        tk.Checkbutton(valve_frame, text="水闸状态", variable=self.valve_state,
                      command=self.toggle_valve).pack(pady=5)

    def create_video_panel(self, parent):
        # 视频显示区域
        self.video_canvas = tk.Canvas(parent, width=640, height=480)
        self.video_canvas.pack(pady=5)
        
        # 控制按钮
        btn_frame = tk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(btn_frame, text="开始监控", command=self.start_video).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="停止监控", command=self.stop_video).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="拍照", command=self.take_snapshot).pack(side=tk.LEFT, padx=5)
        
        # 人流量信息显示
        self.flow_info = tk.Label(parent, text="当前人流量: 0 人")
        self.flow_info.pack(pady=5)

    def create_data_view_button(self, parent):
        """创建数据查看按钮"""
        btn_frame = tk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Button(btn_frame, text="查看历史数据", 
                 command=self.show_data_window).pack(fill=tk.X)

    def show_data_window(self):
        """显示数据查看窗口"""
        data_window = tk.Toplevel(self.root)
        data_window.title("历史数据查看")
        data_window.geometry("800x600")
        
        # 创建选项卡
        notebook = ttk.Notebook(data_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 传感器数据选项卡
        sensor_frame = ttk.Frame(notebook)
        notebook.add(sensor_frame, text="传感器数据")
        self.create_sensor_data_view(sensor_frame)
        
        # 水闸操作记录选项卡
        valve_frame = ttk.Frame(notebook)
        notebook.add(valve_frame, text="水闸操作记录")
        self.create_valve_data_view(valve_frame)
        
        # 用户操作记录选项卡
        user_frame = ttk.Frame(notebook)
        notebook.add(user_frame, text="用户操作记录")
        self.create_user_data_view(user_frame)

    def create_sensor_data_view(self, parent):
        """创建传感器数据视图"""
        # 创建表格
        columns = ("时间", "温度", "湿度", "光照", "人体红外", "烟雾")
        tree = ttk.Treeview(parent, columns=columns, show="headings")
        
        # 设置列标题
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=100)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 加载数据
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT timestamp, temperature, humidity, light, pir, gas 
            FROM sensor_data 
            ORDER BY timestamp DESC 
            LIMIT 100
        ''')
        
        for row in cursor.fetchall():
            tree.insert("", tk.END, values=row)

    def create_valve_data_view(self, parent):
        """创建水闸操作记录视图"""
        columns = ("时间", "操作", "模式", "操作者")
        tree = ttk.Treeview(parent, columns=columns, show="headings")
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150)
        
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT timestamp, operation, mode, operator 
            FROM valve_operations 
            ORDER BY timestamp DESC 
            LIMIT 100
        ''')
        
        for row in cursor.fetchall():
            tree.insert("", tk.END, values=row)

    def create_user_data_view(self, parent):
        """创建用户操作记录视图"""
        columns = ("时间", "操作", "详情")
        tree = ttk.Treeview(parent, columns=columns, show="headings")
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=200)
        
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT timestamp, operation, details 
            FROM user_operations 
            ORDER BY timestamp DESC 
            LIMIT 100
        ''')
        
        for row in cursor.fetchall():
            tree.insert("", tk.END, values=row)

    def get_available_ports(self):
        """获取可用串口列表"""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append(port.device)
        return ports if ports else [""]

    def init_devices(self):
        """初始化设备"""
        self.serial_port = None
        self.camera = None
        self.video_thread = None

    def toggle_serial(self):
        """切换串口状态"""
        if not self.portisopen:
            try:
                self.serial_port = serial.Serial(
                    port=self.port_var.get(),
                    baudrate=int(self.baud_var.get()),
                    timeout=TIMEOUT
                )
                self.portisopen = True
                self.serial_btn.config(text="关闭串口")
                messagebox.showinfo("成功", "串口已打开")
                
                # 启动串口接收线程
                self.is_receiving = True
                self.serial_thread = threading.Thread(target=self.receive_serial_data)
                self.serial_thread.daemon = True
                self.serial_thread.start()
                
            except Exception as e:
                messagebox.showerror("错误", f"无法打开串口: {str(e)}")
        else:
            self.is_receiving = False
            if self.serial_port:
                self.serial_port.close()
            self.portisopen = False
            self.serial_btn.config(text="打开串口")

    def receive_serial_data(self):
        """接收串口数据"""
        while self.is_receiving:
            if self.serial_port and self.serial_port.in_waiting:
                try:
                    # 读取串口数据
                    char = self.serial_port.read().decode()
                    self.serial_buffer += char
                    
                    # 如果收到换行符或回车符，处理完整数据
                    if char in '\n\r':
                        self.process_serial_data(self.serial_buffer.strip())
                        self.serial_buffer = ""
                        
                except Exception as e:
                    logging.error(f"串口数据接收错误: {str(e)}")
            time.sleep(0.01)

    def process_serial_data(self, data):
        """处理串口数据"""
        try:
            if not data:
                return
                
            # 解析数据
            sensor_type = data[0]
            value = ""
            
            if sensor_type == 'g':  # 光强
                value = data[1:]
                self.sensor_data['light'].set(value)
                
            elif sensor_type == 'h':  # 人体红外
                value = data[1:]
                self.sensor_data['pir'].set(value)
                
            elif sensor_type == 'y':  # 烟雾
                value = data[1:]
                self.sensor_data['gas'].set(value)
                
            elif sensor_type == 'w':  # 温湿度组合数据
                try:
                    # 分离温度和湿度数据
                    temp_humi = data.split('&')
                    if len(temp_humi) == 2:
                        # 处理温度
                        temp = temp_humi[0][1:]  # 去掉'w'
                        self.sensor_data['temp'].set(temp)
                        
                        # 处理湿度
                        humi = temp_humi[1][1:].rstrip('!')  # 去掉's'和'!'
                        self.sensor_data['humi'].set(humi)
                except Exception as e:
                    logging.error(f"温湿度数据解析错误: {str(e)}")

            # 自动上报数据
            self.auto_report_sensor_data()
            
        except Exception as e:
            logging.error(f"数据处理错误: {str(e)}")

    def auto_report_sensor_data(self):
        """自动上报传感器数据"""
        try:
            # 获取传感器数据
            data = {
                'temp': float(self.sensor_data['temp'].get()),
                'humi': float(self.sensor_data['humi'].get()),
                'light': float(self.sensor_data['light'].get()),
                'pir': int(self.sensor_data['pir'].get()),
                'gas': int(self.sensor_data['gas'].get())
            }
            
            # 记录数据到数据库
            self.log_sensor_data(data)
            
            # 构建参数字典
            params = {}
            
            # 添加有值的字段
            if data['temp']:
                params["temp"] = {"value": int(data['temp'])}
            if data['humi']:
                params["shidu"] = {"value": int(data['humi'])}
            if data['light']:
                params["guangzhao"] = {"value": int(data['light'])}
            if data['pir']:
                params["rentihongwai"] = {"value": data['pir']}
            if data['gas']:
                params["yanwu"] = {"value": data['gas']}
            
            # 检查阈值
            self.check_thresholds(data)
            
            # 上报到OneNet
            OnenetConnect.report_device_property(params)
                
        except ValueError as e:
            logging.error(f"数据格式错误: {str(e)}")
        except Exception as e:
            logging.error(f"数据上报错误: {str(e)}")

    def report_sensor_data(self):
        """上报传感器数据"""
        try:
            # 获取传感器数据
            data = {
                'temp': float(self.sensor_data['temp'].get()),
                'humi': float(self.sensor_data['humi'].get()),
                'light': float(self.sensor_data['light'].get()),
                'pir': int(self.sensor_data['pir'].get()),
                'gas': int(self.sensor_data['gas'].get())
            }
            
            # 记录数据到数据库
            self.log_sensor_data(data)
            
            # 构建参数字典
            params = {}
            
            # 添加有值的字段
            if data['temp']:
                params["temp"] = {"value": int(data['temp'])}
            if data['humi']:
                params["shidu"] = {"value": int(data['humi'])}
            if data['light']:
                params["guangzhao"] = {"value": int(data['light'])}
            if data['pir']:
                params["rentihongwai"] = {"value": data['pir']}
            if data['gas']:
                params["yanwu"] = {"value": data['gas']}
            
            # 检查阈值
            self.check_thresholds(data)
            
            # 上报到OneNet
            if OnenetConnect.report_device_property(params):
                messagebox.showerror("错误", "数据上报失败")
            else:
                messagebox.showinfo("成功", "数据上报成功")
                
        except ValueError as e:
            messagebox.showerror("错误", "请输入有效的数值")
        except Exception as e:
            messagebox.showerror("错误", f"上报失败: {str(e)}")

    def check_thresholds(self, data):
        """检查传感器数据是否超过阈值"""
        if self.valve_mode.get() == "自动":
            if (data['temp'] > self.temp_threshold.get() or
                data['humi'] > self.humi_threshold.get() or
                data['light'] > self.light_threshold.get()):
                
                if not self.valve_state.get():
                    self.valve_state.set(True)
                    if self.portisopen:
                        self.serial_port.write(b'\x01')
                        messagebox.showinfo("自动控制", "检测到异常，消防水闸已自动打开")

    def toggle_valve(self):
        """控制消防水闸开关"""
        if self.valve_mode.get() == "手动":
            state = self.valve_state.get()
            if self.portisopen:
                # 发送水闸控制命令
                cmd = b'\x01' if state else b'\x00'
                self.serial_port.write(cmd)
                messagebox.showinfo("成功", f"消防水闸已{'打开' if state else '关闭'}")
                # 记录操作
                self.log_valve_operation(
                    "打开" if state else "关闭",
                    self.valve_mode.get()
                )
            else:
                messagebox.showwarning("警告", "串口未打开")
        else:
            messagebox.showinfo("提示", "当前为自动控制模式，无法手动操作")
            # 恢复之前的状态
            self.valve_state.set(not self.valve_state.get())

    def start_video(self):
        """启动视频监控"""
        if not self.is_capturing:
            self.camera = cv2.VideoCapture(0)
            self.is_capturing = True
            self.video_thread = threading.Thread(target=self.update_video)
            self.video_thread.daemon = True
            self.video_thread.start()

    def stop_video(self):
        """停止视频监控"""
        self.is_capturing = False
        if self.camera:
            self.camera.release()

    def update_video(self):
        """更新视频画面"""
        while self.is_capturing:
            ret, frame = self.camera.read()
            if ret:
                # 人流量检测
                results = model1(frame, classes=[0])  # 只检测人
                
                # 获取人数
                people_count = len(results[0].boxes)
                
                # 在画面上标注检测结果
                annotated_frame = results[0].plot()
                
                # 转换图像格式
                image = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(image)
                image = image.resize((640, 480))
                photo = ImageTk.PhotoImage(image=image)
                
                # 更新画面
                self.video_canvas.create_image(0, 0, image=photo, anchor=tk.NW)
                self.video_canvas.photo = photo
                
                # 更新人流量信息
                self.flow_info.config(text=f"当前人流量: {people_count} 人")
                
                # 上报人流量数据
                params = {
                    "people_count_in": {"value": people_count},
                    "people_count_out": {"value": 0},
                    "current_people": {"value": people_count}
                }
                OnenetConnect.report_device_property(params)
            
            time.sleep(0.03)  # 控制帧率

    def take_snapshot(self):
        """拍摄快照"""
        if self.is_capturing:
            ret, frame = self.camera.read()
            if ret:
                filename = f"snapshot_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(filename, frame)
                messagebox.showinfo("成功", f"快照已保存: {filename}")

    def log_sensor_data(self, data):
        """记录传感器数据"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO sensor_data (temperature, humidity, light, pir, gas)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            float(data['temp']),
            float(data['humi']),
            float(data['light']),
            int(data['pir']),
            int(data['gas'])
        ))
        self.conn.commit()

    def log_valve_operation(self, operation, mode):
        """记录水闸操作"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO valve_operations (operation, mode, operator)
            VALUES (?, ?, ?)
        ''', (operation, mode, "系统" if mode == "自动" else "用户"))
        self.conn.commit()

    def __del__(self):
        """清理资源"""
        self.is_receiving = False
        self.stop_video()
        if self.serial_port:
            self.serial_port.close()
        if hasattr(self, 'conn'):
            self.conn.close()

@app.route('/')
def index():
    return """<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>智能室内消防报警系统</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.8/dist/chart.umd.min.js"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: '#4CAF50',
                        secondary: '#2E7D32',
                        danger: '#F44336',
                        warning: '#FFC107',
                        info: '#2196F3',
                        dark: '#333333',
                    },
                    fontFamily: {
                        sans: ['Inter', 'system-ui', 'sans-serif'],
                    },
                }
            }
        }
    </script>
    <style type="text/tailwindcss">
        @layer utilities {
            .content-auto {
                content-visibility: auto;
            }
            .table-hover-row {
                @apply transition-colors duration-200;
            }
            .table-hover-row:hover {
                @apply bg-gray-100;
            }
            .card {
                @apply bg-white rounded-lg shadow-md p-5 mb-5;
            }
            .btn {
                @apply px-4 py-2 rounded-md transition-all duration-200;
            }
            .btn-primary {
                @apply bg-primary text-white hover:bg-secondary;
            }
            .btn-danger {
                @apply bg-danger text-white hover:bg-red-600;
            }
            .alert {
                @apply p-4 rounded-md mb-4;
            }
            .alert-danger {
                @apply bg-red-100 text-red-700 border-l-4 border-red-500;
            }
            .threshold-alert {
                @apply font-bold text-danger;
            }
        }
    </style>
</head>

<body class="bg-gray-50 text-dark">
    <div class="container mx-auto px-4 py-6">
        <!-- 导航栏 -->
        <nav class="bg-primary text-white rounded-lg shadow-md mb-6">
            <div class="container mx-auto px-4">
                <div class="flex justify-between items-center h-16">
                    <div class="flex items-center">
                        <i class="fa fa-fire-extinguisher mr-3 text-2xl"></i>
                        <span class="font-bold text-xl">智能室内消防报警系统</span>
                    </div>
                    <div class="flex items-center space-x-4">
                        <a href="https://open.iot.10086.cn/view/main/index.html#/view2d?id=682d3d1ec7c5e4004002d5d4" 
                           target="_blank" 
                           class="btn btn-primary flex items-center">
                            <i class="fa fa-area-chart mr-2"></i>系统可视化
                        </a>
                    </div>
                </div>
            </div>
        </nav>

        <!-- 概览卡片 -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
            <div class="card bg-gradient-to-r from-blue-500 to-blue-400 text-white">
                <div class="flex justify-between items-center">
                    <div>
                        <p class="text-sm font-medium">当前人数</p>
                        <h3 id="current-people" class="text-3xl font-bold">0</h3>
                    </div>
                    <div class="bg-white/20 p-3 rounded-full">
                        <i class="fa fa-users text-2xl"></i>
                    </div>
                </div>
                <div class="mt-4 flex justify-between text-sm">
                    <span>今日最高: <span id="today-max-people">0</span></span>
                    <span>今日平均: <span id="today-avg-people">0</span></span>
                </div>
            </div>

            <div class="card bg-gradient-to-r from-green-500 to-green-400 text-white">
                <div class="flex justify-between items-center">
                    <div>
                        <p class="text-sm font-medium">消防水闸状态</p>
                        <h3 id="valve-status" class="text-3xl font-bold">关闭</h3>
                    </div>
                    <div class="bg-white/20 p-3 rounded-full">
                        <i class="fa fa-tint text-2xl"></i>
                    </div>
                </div>
                <div class="mt-4">
                    <span class="text-sm">模式: <span id="valve-mode">自动</span></span>
                </div>
            </div>

            <div class="card bg-gradient-to-r from-yellow-500 to-yellow-400 text-white">
                <div class="flex justify-between items-center">
                    <div>
                        <p class="text-sm font-medium">异常警报</p>
                        <h3 id="alert-count" class="text-3xl font-bold">0</h3>
                    </div>
                    <div class="bg-white/20 p-3 rounded-full">
                        <i class="fa fa-bell text-2xl"></i>
                    </div>
                </div>
                <div class="mt-4">
                    <span class="text-sm">最后警报: <span id="last-alert">无</span></span>
                </div>
            </div>
        </div>

        <!-- 实时数据区域 -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
            <!-- 人数趋势图表 -->
            <div class="card lg:col-span-1">
                <h2 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fa fa-line-chart mr-2 text-primary"></i>人数趋势
                </h2>
                <div class="h-64">
                    <canvas id="people-chart"></canvas>
                </div>
                <div class="mt-3 text-sm text-gray-600">
                    <p>更新时间: <span id="chart-update-time">--</span></p>
                </div>
            </div>

            <!-- 传感器数据 -->
            <div class="card lg:col-span-2">
                <h2 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fa fa-dashboard mr-2 text-primary"></i>传感器数据
                </h2>
                <div class="overflow-x-auto">
                    <table class="min-w-full">
                        <thead>
                            <tr class="bg-gray-100">
                                <th class="px-4 py-2 text-left">时间</th>
                                <th class="px-4 py-2 text-left">温度 (°C)</th>
                                <th class="px-4 py-2 text-left">湿度 (%)</th>
                                <th class="px-4 py-2 text-left">光照 (lux)</th>
                                <th class="px-4 py-2 text-left">人体红外</th>
                                <th class="px-4 py-2 text-left">烟雾</th>
                            </tr>
                        </thead>
                        <tbody id="sensor-table-body">
                            <!-- JavaScript will populate this -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- 水闸操作记录 -->
        <div class="card">
            <h2 class="text-xl font-bold mb-4 flex items-center">
                <i class="fa fa-history mr-2 text-primary"></i>水闸操作记录
            </h2>
            <div class="overflow-x-auto">
                <table class="min-w-full">
                    <thead>
                        <tr class="bg-gray-100">
                            <th class="px-4 py-2 text-left">时间</th>
                            <th class="px-4 py-2 text-left">操作</th>
                            <th class="px-4 py-2 text-left">模式</th>
                            <th class="px-4 py-2 text-left">操作者</th>
                        </tr>
                    </thead>
                    <tbody id="valve-table-body">
                        <!-- JavaScript will populate this -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        // 全局变量
        let peopleChart;
        const MAX_PEOPLE_RECORDS = 30; // 图表最多显示30个数据点
        const peopleData = {
            labels: Array(MAX_PEOPLE_RECORDS).fill(''),
            datasets: [{
                label: '实时人数',
                data: Array(MAX_PEOPLE_RECORDS).fill(0),
                borderColor: '#4CAF50',
                backgroundColor: 'rgba(76, 175, 80, 0.1)',
                borderWidth: 2,
                tension: 0.4,
                fill: true
            }]
        };

        // 初始化图表
        function initPeopleChart() {
            const ctx = document.getElementById('people-chart').getContext('2d');
            peopleChart = new Chart(ctx, {
                type: 'line',
                data: peopleData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                display: false
                            }
                        },
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(0, 0, 0, 0.05)'
                            }
                        }
                    },
                    animation: {
                        duration: 500
                    }
                }
            });
        }

        // 更新人数数据
        function updatePeopleData() {
            fetch('/get_people_data')
              .then(response => response.json())
              .then(data => {
                    // 更新当前人数
                    document.getElementById('current-people').textContent = data.current || 0;
                    document.getElementById('today-max-people').textContent = data.today_max || 0;
                    document.getElementById('today-avg-people').textContent = (data.today_avg || 0).toFixed(1);
                    
                    // 更新图表
                    if (peopleChart) {
                        // 移除最早的数据点并添加新的数据点
                        peopleData.datasets[0].data.shift();
                        peopleData.datasets[0].data.push(data.current || 0);
                        peopleChart.update();
                    }
                });
        }

        // 更新传感器数据
        function updateSensorData() {
            fetch('/get_sensor_data')
              .then(response => response.json())
              .then(data => {
                    const tableBody = document.getElementById('sensor-table-body');
                    tableBody.innerHTML = '';
                    data.forEach(item => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td class="px-4 py-2">${item.timestamp}</td>
                            <td class="px-4 py-2">${item.temperature}</td>
                            <td class="px-4 py-2">${item.humidity}</td>
                            <td class="px-4 py-2">${item.light}</td>
                            <td class="px-4 py-2">${item.pir}</td>
                            <td class="px-4 py-2">${item.gas}</td>
                        `;
                        tableBody.appendChild(row);
                    });
                });
        }

        // 更新水闸操作数据
        function updateValveData() {
            fetch('/get_valve_data')
              .then(response => response.json())
              .then(data => {
                    const tableBody = document.getElementById('valve-table-body');
                    tableBody.innerHTML = '';
                    data.forEach(item => {
                        const row = document.createElement('tr');
                        const operationIcon = item.operation === '打开' ? '<i class="fa fa-toggle-on text-green-500"></i>' : '<i class="fa fa-toggle-off text-gray-500"></i>';
                        row.innerHTML = `
                            <td class="px-4 py-2">${item.timestamp}</td>
                            <td class="px-4 py-2">${operationIcon}</td>
                            <td class="px-4 py-2">${item.mode}</td>
                            <td class="px-4 py-2">${item.operator}</td>
                        `;
                        tableBody.appendChild(row);
                    });
                });
        }

        // 更新水闸状态
        function updateValveStatus() {
            fetch('/get_valve_status')
              .then(response => response.json())
              .then(data => {
                    document.getElementById('valve-status').textContent = data.status ? '打开' : '关闭';
                    document.getElementById('valve-mode').textContent = data.mode;
                });
        }

        // 初始化函数
        function init() {
            initPeopleChart();
            updatePeopleData();
            updateSensorData();
            updateValveData();
            updateValveStatus();

            // 定时更新数据
            setInterval(updatePeopleData, 5000);
            setInterval(updateSensorData, 5000);
            setInterval(updateValveData, 5000);
            setInterval(updateValveStatus, 5000);
        }

        window.onload = init;
    </script>
</body>

</html>
"""

@app.route('/get_people_data')
def get_people_data():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect('smart_monitor.db')
    cursor = conn.cursor()

    # 获取当前人数
    cursor.execute('''
        SELECT count FROM people_flow 
        ORDER BY timestamp DESC 
        LIMIT 1
    ''')
    current_row = cursor.fetchone()
    current = current_row[0] if current_row else 0

    # 获取今日最高人数
    cursor.execute('''
        SELECT MAX(count) FROM people_flow 
        WHERE timestamp >= ?
    ''', (today + ' 00:00:00',))
    max_row = cursor.fetchone()
    today_max = max_row[0] if max_row and max_row[0] else 0

    # 获取今日平均人数
    cursor.execute('''
        SELECT AVG(count) FROM people_flow 
        WHERE timestamp >= ?
    ''', (today + ' 00:00:00',))
    avg_row = cursor.fetchone()
    today_avg = avg_row[0] if avg_row and avg_row[0] else 0

    conn.close()

    return jsonify({
        'current': current,
        'today_max': today_max,
        'today_avg': today_avg
    })

@app.route('/get_sensor_data')
def get_sensor_data():
    conn = sqlite3.connect('smart_monitor.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, temperature, humidity, light, pir, gas 
        FROM sensor_data 
        ORDER BY timestamp DESC 
        LIMIT 10
    ''')
    rows = cursor.fetchall()
    data = []
    for row in rows:
        data.append({
            'timestamp': row[0],
            'temperature': row[1],
            'humidity': row[2],
            'light': row[3],
            'pir': row[4],
            'gas': row[5]
        })
    conn.close()
    return jsonify(data)

@app.route('/get_valve_data')
def get_valve_data():
    conn = sqlite3.connect('smart_monitor.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, operation, mode, operator 
        FROM valve_operations 
        ORDER BY timestamp DESC 
        LIMIT 10
    ''')
    rows = cursor.fetchall()
    data = []
    for row in rows:
        data.append({
            'timestamp': row[0],
            'operation': row[1],
            'mode': row[2],
            'operator': row[3]
        })
    conn.close()
    return jsonify(data)

@app.route('/get_valve_status')
def get_valve_status():
    return jsonify({
        'status': app.monitor_system.valve_state.get(),
        'mode': app.monitor_system.valve_mode.get()
    })

def main():
    root = tk.Tk()
    app.monitor_system = SmartMonitorSystem(root)
    
    # 启动Flask服务器
    flask_thread = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 5000})
    flask_thread.daemon = True
    flask_thread.start()
    
    root.mainloop()

if __name__ == "__main__":
    main() 