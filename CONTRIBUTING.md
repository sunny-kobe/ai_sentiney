# 🤝 Contributing to Project Sentinel

感谢你对 **Project Sentinel** 感兴趣！我们非常欢迎社区的贡献，帮助每一个散户拥有更强大的投顾工具。

## 如何开始

1.  **Fork 本仓库**: 点击右上角的 "Fork" 按钮。
2.  **克隆到本地**:
    ```bash
    git clone https://github.com/your-username/ai_sentiney.git
    cd ai_sentiney
    ```
3.  **创建分支**:
    ```bash
    git checkout -b feature/amazing-new-feature
    ```

## 开发规范

- **代码风格**: 请遵循 Python PEP8 规范。
- **依赖管理**: 如果引入了新的库，请务必更新 `requirements.txt`。
- **文档**: 如果修改了配置或运行方式，请同步更新 `README.md`。

## 提交 Pull Request (PR)

1.  确保你的代码在本地运行无误（建议先使用 `--dry-run` 模式测试）。
2.  提交更改并 Push 到你的 Fork 仓库。
3.  在 GitHub 上发起 Pull Request，并简要描述你的修改内容。

## 想要贡献什么？

- **新的数据源**: 接入更多维度的数据（如期权、宏观经济指标）。
- **新的策略**: 在 `DataProcessor` 中实现更多的技术指标。
- **Prompt 优化**: 改进 `config.yaml` 中的 System Prompt，让 Gemini 的分析更准确。
- **UI 改进**: 优化飞书卡片的展示效果，或接入其他推送渠道（钉钉、企业微信、Telegram）。

再次感谢你的贡献！🚀
