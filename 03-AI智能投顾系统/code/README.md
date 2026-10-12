# 源码说明

本目录是从基座项目中**单独抽取出来的、由我实现的部分**。基座代码（行情接入、账户体系、策略引擎等）
未包含在此。

> **不可直接运行**：这些文件依赖基座的框架（Flask 蓝图注册、`login_required` 装饰器、
> LLMService 等）。这里放出来是为了让实现可被阅读与验证，不是可独立启动的项目。

---

## 文件清单

### 后端

| 文件 | 行数 | 说明 |
|---|---|---|
| [`backend/fund_advisor.py`](./backend/fund_advisor.py) | 897 | **投顾模块主体** —— 13 个 REST 接口 |
| [`backend/indicator_warehouse.py`](./backend/indicator_warehouse.py) | 74 | 指标仓库接口 |
| [`backend/factor_eval.py`](./backend/factor_eval.py) | 142 | 因子有效性评估（IC / Rank IC） |

### 前端

| 文件 | 行数 | 说明 |
|---|---|---|
| [`frontend/views/fund-advisor/index.vue`](./frontend/views/fund-advisor/index.vue) | 502 | 投顾主页面 |
| [`frontend/api/fund-advisor.js`](./frontend/api/fund-advisor.js) | 53 | 接口封装 |

**合计 1,668 行。**

---

## 阅读建议

如果只想看最核心的部分，按这个顺序：

1. **`fund_advisor.py` 的 `chat()`（约 101-200 行）** —— AI 对话式投顾：
   实时行情组装成上下文注入 prompt + 滑动窗口多轮记忆 + 三级降级
2. **`get_themes()`** —— 主题趋势评分，把 ETF 按主题聚合打分
3. **`get_valuation()`** —— 估值分位，指数 PE 的历史百分位
4. **`factor_eval.py`** —— IC / Rank IC 的日频横截面实现

---

## 说明

- 代码中所有**密钥均通过环境变量读取**（如 `os.getenv("DEEPSEEK_API_KEY")`），无硬编码凭据。
- 行情数据源使用公开接口（腾讯行情、中证指数）。
