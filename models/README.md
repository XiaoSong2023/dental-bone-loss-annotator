# 已配置的离线牙科权重

版本：1.1.0-ai-preview。模型在本地 CPU 运行，不需要 CUDA，也不在线下载。
首次自动分析依次执行牙齿实例分割、真实牙框扩展裁剪、牙面三点识别和坐标逆变换。
三点是 CEJ（釉牙骨质界）、AC/bone-level（骨嵴与牙面交点）和 apex（根尖）。
旧软件中的 CEJ-2mm 不属于本模型输出，保持空缺，不能由固定像素距离代替。

|用途|来源与固定版本|文件及 SHA-256|
|---|---|---|
|全景片分割与 FDI 候选|[chocodo/teeth-segmentation-odontoai](https://huggingface.co/chocodo/teeth-segmentation-odontoai/tree/4867533fb8e8ccd115c10c533a238e4288757165)，Mask R-CNN ResNet50 FPN，背景+52牙位类|`chocodo--teeth-segmentation-odontoai/best.pth`；`37bb200f5aa6620fc58fe549d8babd0080b6d2b661d1e33ec452ea3f329f7012`|
|牙面三点候选|[rummanadib023/denpar-bone-loss-v2](https://huggingface.co/rummanadib023/denpar-bone-loss-v2/tree/d254abd6df9ab41c0367b99457334d7f1ea69895)，YOLOv8m-pose ONNX，768输入|`rummanadib023--denpar-bone-loss-v2/surf_pose.onnx`；`60d14e5b6560cbf834ffd0a6aff0c0558390224bbe1902199931479bfb89ad98`|

分割模型卡声明 MIT；三点 ONNX 元数据声明 AGPL-3.0（元数据链接 https://ultralytics.com/license），该发布者模型卡未额外列明许可证。保留这些声明与来源，不为既有用户软件擅自指定许可证。此包供本项目本地使用及复核，尚未完成外部分发许可审查。随附 THIRD_PARTY 与 SOURCE 文件夹记录依赖许可和本次集成源代码。

这两份均是已训练权重。本次集成训练步数为 0；加载分割参数采用 tensor-only `weights_only=True`、严格键检查及固定 SHA。软件不用 COCO 参数作为牙科结果，不执行社区完整对象 `.pt` pickle。原购买源码、原指定 GitHub 项目均保留在独立审计工作区；本版本采用独立标明的社区模型，不是这两个原项目的配套权重。

验证范围：一张实际全景片自动分割得到31颗牙；完整三点候选17组、51点，覆盖11颗牙（最终原始 JPG 后端验证）。20颗牙未检出完整三点。已完成原图坐标回映；分割结果与上游结构的数值对照一致。尚无该用户全景片域的准确率验证，也没有每牙完整点位保证。图像左右候选需要人工确认近远中；漏检留空，错误可拖动、删除或补标。
