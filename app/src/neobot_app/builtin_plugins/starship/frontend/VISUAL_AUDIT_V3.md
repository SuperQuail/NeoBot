# 第三轮视觉校型：护盾、四单位、舰体

## 可见护盾

新增 `world/shield.ts`：前方三块、侧方六块及一片弧顶，共10块实际曲面。蓝色透光底色、掠射角增亮、可见接缝、弱蜂窝与缓慢波纹；场景中的发射节点说明边界来源。材质保留对数深度且不写深度缓冲，不使用相机覆盖图片冒充玻璃。

## 逐个检查的原作参考

### 追猎者
- [高清结构图](https://static.wikia.nocookie.net/starcraft/images/b/b7/Stalker_SC-FM_Art1.jpg/revision/latest)
- [原作渲染](https://static.wikia.nocookie.net/starcraft/images/b/bd/Stalker_SC2_Rend1.png/revision/latest)
- [概念图](https://static.wikia.nocookie.net/starcraft/images/8/88/Stalker_SC2_Cncpt1.jpg/revision/latest)
- 上版偏差：过大的独立圆盘、薄而直的冠、欠缺鼻额结构、直杆腿及悬挂纸盾。目标是厚覆甲、前倾冠脊、嵌入式椭圆窗和关节刀足。

### 龙骑士
- [结构图](https://static.wikia.nocookie.net/starcraft/images/7/78/Dragoon_SC-FM_Art1.jpg/revision/latest)
- [金蓝原作渲染](https://static.wikia.nocookie.net/starcraft/images/1/1f/Dragoon_SC2-LotV_Rend1.jpg/revision/latest)
- [游戏中的结构视角](https://static.wikia.nocookie.net/starcraft/images/2/28/Dragoon_SC2-LotV_Game1.jpg/revision/latest)
- 上版偏差：四个光滑球肩、整球躯体、缺下切腹甲与足部结构。第三张是不同皮肤，仅用于结构核对，不替换标准配色。

### 不朽者
- [高清技术结构图](https://static.wikia.nocookie.net/starcraft/images/d/d3/Immortal_SC-FM_Art1.jpg/revision/latest)
- [原作渲染](https://static.wikia.nocookie.net/starcraft/images/6/6f/Immortal_SC2_Rend1.jpg/revision/latest)
- [原作概念](https://static.wikia.nocookie.net/starcraft/images/e/e8/Immortal_SC2_Cncpt1.jpg/revision/latest)
- 上版偏差：圆滑香蕉状躯干、裸露细炮管、缺武器舱包覆、肩胛与分段足甲。应是厚重的装甲火炮平台。

### 巨像
- [原作渲染](https://static.wikia.nocookie.net/starcraft/images/6/62/Colossus_SC2_Rend1.jpg/revision/latest)
- [原作概念](https://static.wikia.nocookie.net/starcraft/images/9/92/Colossus_SC2_Cncpt2.jpg/revision/latest)
- [另一阵营的实机结构视角](https://static.wikia.nocookie.net/starcraft/images/7/7d/Colossus_SC2-LotV_Game3.jpg/revision/latest)
- 上版偏差：小水滴头立在四根长杆上。需要提高躯体占比、形成前倾分段厚甲、腹肋、大侧能量板、膝甲和多关节足。第三张为净化者版本，只参考结构。

## 暴雪官方动画姿态核对

[卡拉克斯官方介绍](https://news.blizzard.com/en-us/article/19975211/karax-now-available-in-legacy-of-the-void-co-op-missions)提供了50帧动画图条：[不朽者](https://bnetcmsus-a.akamaihd.net/cms/content_entry_media/IU53DZB3ZGAF1449623504023.png)、[巨像](https://bnetcmsus-a.akamaihd.net/cms/content_entry_media/P8W979AHKOO51449623503812.png)。研究中按CSS规定的123.5×136帧宽准确抽取姿态核对（6175×136原图、50帧、6秒）。这些是动画姿态，不是均匀相机方位的360°扫描；巨像是净化者外观，结构可参考，不能直接当作金蓝默认皮肤。

## 舰体前后对照

- [前视角](https://static.wikia.nocookie.net/starcraft/images/3/32/Spear_of_Adun_Front_LotV.jpg/revision/latest)
- [后视角](https://static.wikia.nocookie.net/starcraft/images/1/19/Spear_of_Adun_Rear_LotV.jpg/revision/latest)
- 上版主要问题：等厚平板与水平刀片架。后视图显示了厚舱壁、纵向肋板、立体冠架、多喷口和被装甲包覆的能量腔；细化必须先补这些体积，而非只增加平面纹样。

本轮维持内饰米制、74.4公里实际外壳和既有三维操作能力。所有模型是参考重建；不把不明许可的游戏提取文件直接纳入发行包。

## 实机发现并修复的问题

- 曲面主壳与外覆甲交叉造成锯齿碎边：对齐舰体折点/纵向站位，调整不朽者肩壳及巨像额冠层间净距。
- 龙骑士胫部黑芯穿甲：缩小承力芯、保留膝踝外露结构。
- 大尺度外壳把车间下层深井盖成金色平面：只在两翼内部舱腔位置裁去外壳渲染，保留步行板及边界碰撞。
- 材质克隆后合金着色器重复注入：修复编译链幂等性，并加入回归测试。
- 全舰远景的巨大白色光斑：逐对象实机隔离确认是护盾在亚像素MSAA采样时UV越界，使边缘指数项溢出；钳制UV、距离与Fresnel输入后，近景蓝色场保留，远景白斑消失。不是通过隐藏护盾或关闭辉光掩盖。

仍有差距：模型没有原作完整贴图、密集内部机件及全部细小雕纹；曲率和部分装甲分片仍为参考重建，不能称为原游戏资产或1:1复刻。
