# Weather Landscape 插件

基于 OpenWeatherMap 的横屏风景天气图：左侧房子与时钟，右侧一条温度曲线贯穿全宽，
曲线上分布云、雨、雪、风向树与正午/午夜的花，壁炉烟雾的倾角随当地气压变化。

## 请求方式

```text
http://127.0.0.1:5000/weather_landscape/view/weather_landscape?size=hxl&lat=36.7066&lon=119.1268&key=<API Key>
```

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `size` | **必填** | `hxl`（384×184）或 `h2xl`（400×300），两者是独立布局 |
| `key` | 空 | OpenWeatherMap API Key；为空时请求上游会失败 |
| `lat` / `lon` | `0.0` | 纬度 / 经度 |
| `units` | `0` | `0` 摄氏度，`1` 华氏度 |
| `pressure_min` / `pressure_max` | `980.0` / `1030.0` | 气压区间，用来把当前气压映射成烟雾倾角 |
| `tz` | 框架默认时区 | 时区偏移（小时）或 `ZoneInfo` 名称；图上一切时刻都按它换算 |
| `rotate` / `invert` / `format` | 框架默认 | 旋转、反色、输出格式，由框架统一处理后处理 |

## 目录结构

- `lib/weather_landscape_fetcher.py`：取数。并发请求实况与预报两个端点，并把结果规整成
  按时间升序的天气序列；`SunCalculator` 负责日出/日落/太阳正午，时间一律是该插件时区下的本地时间。
- `view/weather_landscape/drawer.py`：绘制引擎，`hxl` 与 `h2xl` 共用。几何参数由视图传入，
  所以两套布局互不影响。
- `view/weather_landscape/hxl.py`、`h2xl.py`：两种尺寸各自的坐标与信息带。
- `assets/sprite/`：点阵素材。素材索引是 0=黑 1=白 2=红 3=透明，框架画布是 0=白 1=黑 2=红，
  引擎载入时会重映射并生成掩膜，贴图走 `Image.paste()`。

## 渲染要点

- 云端素材首次使用后进程内缓存，热重载时随模块一起重建。
- 曲线、降水、风向都是先算好一维的分段数组再落笔，没有整屏的逐像素循环。
