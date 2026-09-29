# 原作参考与本轮美术重构

## 实际查看的原作图

1. [暴雪《虚空之遗》战役预览](https://news.blizzard.com/en-gb/article/16668520/legacy-of-the-void-campaign-preview)：[舰桥](https://bnetcmsus-a.akamaihd.net/cms/content_folder_media/pq/PQFTXO2GMZ6A1415237281750.jpg)、[战争议会](https://bnetcmsus-a.akamaihd.net/cms/content_folder_media/me/MESBCIBRXW361415237434393.jpg)、[太阳核心](https://bnetcmsus-a.akamaihd.net/cms/content_folder_media/r2/R2ENCXY6TTCZ1415234276295.jpg)。
2. [亚顿之矛原作模型图](https://static.wikia.nocookie.net/starcraft/images/3/32/Spear_of_Adun_Front_LotV.jpg/revision/latest?cb=20200819095311)。
3. [Simon Fuchs 的原作高模说明](https://simonfuchs.wordpress.com/2016/02/13/artwork-starcraft-ii-legacy-of-the-void-spear-of-adun-highpoly/)：模型作者Simon Fuchs，概念设计Justin Thavirat。其图源失效/部分ArtStation访问失败，不将未成功打开的图片当作已检查依据。

以上图片仅作为设计对照，未作为游戏背景或假3D界面贴入游戏。原作版权归其权利人；本工程模型是按视觉参考重新构建的几何。

## 推翻旧版的判断

- 舰体不是香蕉状实心叶片束。它具有巨大的负空间、桥接宽梁、带孔冠架、短宽装甲刃、蓝灰内甲以及明显的椭圆能量核心。
- 舰桥不是重复细管拱组成的玻璃温室。主视觉是近处低矮圆形星图台，远处横向展开的厚重弯翼框架，侧方大体块建筑围合宽阔太空景观。
- 控制台不是竖直六格自动售货机。分片厚甲、暗内衬、盾徽、圆形能量池及悬浮星图才是设备主体，业务按钮嵌于弧形操作沿。
- 战争议会不是同层玻璃展厅。多层悬挑平台、巨型弯支架、深蓝色空间和重复机械龛制造巨大纵深。
- 原作材质并非镜面亮黄金。古金/青铜低饱和大面、蓝灰内嵌、窄边高光、深色雕线和少量灵能光共同塑形。强噪声微纹理和全局过曝应移除。

## 美术优先级

1. 主轮廓与负空间；2. 入场镜头的前中后景；3. 大面/边缘/嵌槽的材质分区；4. 冷暖光比；5. 原作标志性的圆台、盾徽、弯翼、椭圆宝石；最后再增加小刻纹。

既有功能契约保持：74.4公里真实外壳、米制步行区域、连续通路、六类实体业务设备、三维操作仪和中文命名、真实接口与确认保护。不用原作截图覆盖模型冒充实现。

## 星灵战争机械参考

按用户要求，装配工位不再使用泛科幻机体；已搜索并实际查看：

- [追猎者模型图](https://static.wikia.nocookie.net/starcraft/images/b/bd/Stalker_SC2_Rend1.png/revision/latest)：高竖向深紫甲壳、侧面圆能量透镜、四刃足。
- [龙骑士模型图](https://static.wikia.nocookie.net/starcraft/images/1/1f/Dragoon_SC2-LotV_Rend1.jpg/revision/latest)：低宽穹甲、蓝脊、四个大肩甲与展开粗腿。
- [不朽者模型图](https://static.wikia.nocookie.net/starcraft/images/6/6f/Immortal_SC2_Rend1.jpg/revision/latest)：四足重甲、中央高拱护盖、左右前伸双炮。
- [巨像模型图](https://static.wikia.nocookie.net/starcraft/images/6/62/Colossus_SC2_Rend1.jpg/revision/latest)：高悬长水滴躯体、四根长刀足、蓝色椭圆能量窗及热射线阵列。
- [暴雪单位演变文章](https://news.blizzard.com/en-gb/article/21509420/evolution-complete-reimagining-classic-starcraft-units-for-starcraft-ii)：辅助理解龙骑士、不朽者与追猎者的形态差异。

这些是按原作特征重新建模的静态装配展品，未导入或假称拥有原游戏模型；单位大小用于舰内展示比例，不将未经证实的尺寸称为官方设定。
