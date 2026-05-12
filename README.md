# VLA Course

VLA Course 是 Xbotics Embodied AI Lab 的具身智能与 Vision-Language-Action 课程代码资料仓库。仓库按课程大纲组织代码、Notebook 和机器人模型资料，便于学员按章节获取实验材料。

## 目录结构

```text
.
├── 第一部分：基础篇/
│   └── 第2章：具身智能基础工具与框架/
├── 第二部分：环境和数采/
│   ├── 第3章：机器人基础与实操/
│   └── 第4章：VLA数据采集和处理/
├── 第三部分：基础VLA算法/
│   ├── 第5章：生成式机器人策略/
│   └── 第6章：常见VLA算法/
├── 第四部分：VLA算法的后训练/
│   ├── 第7章：VLA算法的微调/
│   ├── 第8章：Sim2Real及Real2Sim/
│   ├── 第9章：科研臂VLA实践/
│   └── 第10章：VLA技术总结与前沿展望/
```

当前已包含的主要资料：

- `第一部分：基础篇/第2章：具身智能基础工具与框架/2.1 PyTorch及PyTorchLightning框架/code.zip`
- `第一部分：基础篇/第2章：具身智能基础工具与框架/2.2 Transformer核心原理/URDF.zip`
- `第一部分：基础篇/第2章：具身智能基础工具与框架/2.3 GPT2的实现/code.zip`
- `第二部分：环境和数采/第3章：机器人基础与实操/3.1 机器人核心数学基础/URDF.zip`
- `第二部分：环境和数采/第3章：机器人基础与实操/3.3 LeRobot框架/pyproject.toml`
- `第二部分：环境和数采/第3章：机器人基础与实操/3.4 LIBERO仿真环境/libero_demo.ipynb`

部分章节目录目前作为课程大纲占位保留，后续可逐步补充实验代码、讲义配套材料或 README。

## 使用方式

克隆仓库：

```bash
git clone https://github.com/Xbotics-Embodied-AI-Lab/VLA-Course.git
cd VLA-Course
```

按章节进入对应目录，解压 `code.zip` 或 `URDF.zip` 后运行课程代码。各章节代码可能有独立依赖，请优先查看对应目录中的 `pyproject.toml`、Notebook 或压缩包内说明。

## 维护约定

- 课程资料按“部分 / 章节 / 小节”目录放置。
- 大型模型权重、数据集、录屏、课件 PDF/PPT 不建议直接提交到 Git；可在章节 README 中提供下载说明。
- 本地浏览器状态、登录态、缓存和临时下载文件不会提交到仓库。
