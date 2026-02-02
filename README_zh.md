# Mobile Portainer API

[English](README.md) | [中文](README_zh.md)

这是一个基于 [FastAPI](https://fastapi.tiangolo.com/) 构建的轻量级 Docker 管理 API 服务。它旨在为移动端应用提供简洁的 Docker 容器、镜像、网络和卷的管理接口，同时也包含了一个简单的 Web 管理界面用于管理 API 密钥和集群节点。

## ✨ 主要功能

- **Docker 管理**:
  - **容器 (Containers)**: 获取列表、查看详情、查看日志、资源统计、启动、停止、重启、强制停止、删除、**浏览文件**。
  - **镜像 (Images)**: 镜像列表查询、拉取新镜像、删除镜像、查看镜像详情。
  - **网络 (Networks)**: 网络列表、查看网络详情、创建网络、删除网络。
  - **卷 (Volumes)**: 卷列表、查看卷详情、创建卷、删除卷、**浏览文件**。
  - **系统 (System)**: 获取 Docker 系统信息、版本信息、实时事件流 (Events)。
- **安全认证**:
  - 核心 API 接口采用 `X-API-Key` 进行访问控制。
  - Web 管理后台采用 Basic Auth 登录保护。
- **Web 管理界面**:
  - 提供直观的界面管理 API 访问密钥 (API Keys)。
  - 管理多节点集群信息 (Cluster Nodes)。
- **自动更新**:
  - 内置 Git 自动更新服务，可配置定时检查远程仓库并自动更新重启。
- **系统监控**:
  - 支持挂载宿主机根目录，用于监控宿主机资源使用情况。

## 🛠️ 技术栈

- **编程语言**: Python 3.9+
- **Web 框架**: FastAPI
- **数据库**: SQLite (通过 SQLAlchemy ORM 管理)
- **Docker 交互**: Docker SDK for Python
- **部署方式**: Docker / Docker Compose

## 🚀 快速开始

### 1. 前置要求

确保你的服务器上已安装：
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

### 2. 安装与运行

直接使用 Docker Compose 启动服务：

```bash
# 构建并后台启动
docker-compose up -d --build
```

### 3. 访问服务

启动成功后，可以通过以下地址访问：

- **Web 管理后台**: [http://localhost:8000](http://localhost:8000)
  - 默认用户名: `admin`
  - 默认密码: `password`
  - *请在生产环境中修改 `docker-compose.yml` 中的默认密码！*
- **API 文档 (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API 文档 (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## ⚙️ 环境变量配置

可以通过修改 `docker-compose.yml` 中的 `environment` 部分来配置服务：

| 变量名 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `ADMIN_USER` | `admin` | Web 管理界面的登录用户名 |
| `ADMIN_PASSWORD` | `...` | Web 管理界面的登录密码 |
| `IGNORED_EVENTS` | `exec_create,exec_start,exec_die` | Docker 事件流中忽略的事件类型 |
| `GIT_AUTO_UPDATE` | `true` | 是否开启 Git 自动更新功能 |
| `GIT_REPO_URL` | `...` | 自动更新拉取的 Git 仓库地址 |
| `GIT_BRANCH` | `main` | 跟踪的 Git 分支 |
| `GIT_CHECK_INTERVAL` | `60` | 自动更新检查间隔（秒） |
| `GIT_USER` | `...` | Git 仓库用户名 (如果需要) |
| `GIT_PASSWORD` | `...` | Git 仓库密码 (如果需要) |
| `HOST_FILESYSTEM_ROOT` | `/hostfs` | 宿主机根目录在容器内的挂载路径 |

## 📂 项目结构

```text
.
├── app/
│   ├── core/           # 核心配置、安全认证、工具函数
│   ├── db/             # 数据库模型 (Models) 与连接 (Database)
│   ├── routers/        # API 路由模块 (Containers, Images, WebUI 等)
│   ├── services/       # 后台服务 (Docker Event Listener, Git Updater)
├── data/               # 数据持久化目录 (SQLite 数据库文件)
├── docker-compose.yml  # Docker Compose 编排文件
├── Dockerfile          # Docker 镜像构建文件
├── main.py             # FastAPI 应用入口
└── requirements.txt    # Python 依赖列表
```

## 📝 API 调用示例

所有受保护的 API 接口都需要在 HTTP Header 中包含 `X-API-Key`。

**获取容器列表:**

```http
GET /containers/json HTTP/1.1
Host: localhost:8000
X-API-Key: <在Web界面生成的API Key>
```

你可以在 Web 管理界面 (`/`) 登录后生成和管理这些 API Key。
