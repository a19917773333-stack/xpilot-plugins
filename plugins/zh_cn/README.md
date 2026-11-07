# 简体中文增强 1.1.0

独立开关 ExtChineseUiEnabled，使用现有宿主 ui_translation 接口。只改变界面翻译。

按用户要求直接采用 juyun86/chinese_ui 1.1.0 的完整 3161 条词库，重叠词条以该包为准，
保留本地独有的 77 条导航与插件词条，共 3238 条。导航距离中的 m 按上下文显示为米。
参考提交：2c35df28fd623ef88a5f4e66e668bdbd0c5d8e20。
来源：https://github.com/juyun86/xpilot-plugins/tree/2c35df28fd623ef88a5f4e66e668bdbd0c5d8e20/plugins/chinese_ui
该包声明基础翻译来自旧版 sunnypilot。未引入其车辆控制、商店来源或其他插件。

字体为未经修改的 Noto Sans CJK SC Regular 2.004，许可证见 FONT-LICENSE.txt。
关闭后恢复基础语言，不写 LanguageSetting。未知动态文本和第三方名称仍可能保留原文。
