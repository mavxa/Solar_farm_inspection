# Инспекция солнечной фермы

## Демонстрация

- Просмотр: https://rutube.ru/video/private/9a565140615dd2a88e00a43022babae3/?p=D9bHZGmMB7lim2hGRaDhrQ
- Скачать видео: https://drive.google.com/file/d/1Ud2coed4hlWKt3O1LneeI_CeDVL_ZYq8/view?usp=sharing

Решение для отборочного этапа соревнования `Инспекция солнечной фермы`: генерация мира Gazebo с солнечными панелями, автономный облёт на Clover, распознавание состояния панелей через YOLO, публикация результата в `/solar` и автоматический отчёт.

English version: [`README.en.md`](README.en.md).

## Что Делает Решение

- Генерирует Gazebo-мир на базе стандартного Clover ArUco world.
- Размещает 5 солнечных панелей внутри ArUco-поля.
- Размещает цветные индикаторы состояния: `yellow`, `orange`, `red`.
- Размещает 2-5 зелёных загрязнений на каждой панели.
- Запускает автономную миссию облёта 5 панелей.
- Распознаёт `solar_panel`, `contamination`, `indicator_yellow`, `indicator_orange`, `indicator_red` через YOLOv8n.
- Публикует аннотированное изображение в ROS-топик `/solar` с типом `sensor_msgs/Image`.
- Выводит результат в терминал.
- Сохраняет отчёт в `reports/solar_report.txt`.
- Управляет LED-индикацией через `led/set_effect`, если сервис доступен.

## Структура

```text
docs/                         PDF с регламентом
models/solar_panel/            Gazebo-модель солнечной панели
scripts/generate_world.py      генератор мира
scripts/inspect_solar.py       основная автономная миссия
scripts/use_solar_world.sh     подмена Clover world на сгенерированный
scripts/install_gazebo_models.sh установка модели solar_panel в Gazebo
weights/solar_yolov8n_best.pt  обученная YOLOv8n-модель
worlds/generated_solar.world   сгенерированный мир
README.en.md                   английская версия инструкции
```

## Требования

- ROS Noetic / ROS1 в образе Clover.
- Gazebo 11.
- Рабочий Clover simulation с ArUco world.
- Python 3.8 в VM.
- Доступ к интернету для первичной установки Python-зависимостей.

Проверялось в Clover VM, запущенной через QEMU/KVM.

## Установка С Нуля

Клонировать репозиторий:

```bash
cd ~/scripts
git clone https://github.com/mavxa/Solar_farm_inspectio.git Solar_farm_inspection
cd Solar_farm_inspection
```

Если используется SSH:

```bash
cd ~/scripts
git clone git@github.com:mavxa/Solar_farm_inspectio.git Solar_farm_inspection
cd Solar_farm_inspection
```

Сделать скрипты исполняемыми:

```bash
chmod +x scripts/*.py scripts/*.sh
```

Подключить ROS-окружение:

```bash
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash 2>/dev/null || source ~/catkin_ws/install/setup.bash
```

Создать Python-окружение. Важно использовать `--system-site-packages`, чтобы Python видел системные ROS-пакеты (`rospy`, `cv_bridge`, `clover`).

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -U pip
```

Установить CPU-only PyTorch. Это важно: обычный `pip install ultralytics` может скачать CUDA/NVIDIA-пакеты на несколько гигабайт и забить диск VM.

```bash
pip install torch==2.4.1+cpu torchvision==0.19.1+cpu \
  --index-url https://download.pytorch.org/whl/cpu
```

Установить Ultralytics и остальные зависимости:

```bash
pip install ultralytics==8.4.80 --no-deps
pip install numpy==1.24.4 opencv-python-headless pillow matplotlib psutil requests polars ultralytics-thop
```

Проверить окружение:

```bash
python - <<'PY'
import torch
import ultralytics
import cv2
import rospy
print('torch:', torch.__version__)
print('cuda:', torch.cuda.is_available())
print('ultralytics:', ultralytics.__version__)
print('cv2:', cv2.__version__)
print('rospy: ok')
PY
```

Ожидаемо: `cuda: False`.

## Подготовка Gazebo-Моделей

Чтобы Gazebo находил `model://solar_panel` даже после перезагрузки VM:

```bash
scripts/install_gazebo_models.sh
```

Скрипт создаёт ссылку:

```text
~/.gazebo/models/solar_panel -> ~/scripts/Solar_farm_inspection/models/solar_panel
```

## Генерация Мира

Сгенерировать случайный мир на базе Clover ArUco world:

```bash
python3 scripts/generate_world.py \
  --base-world ~/scripts/basic_worlds/worlds/clover_aruco.world \
  --output worlds/generated_solar.world \
  --truth-output worlds/generated_truth.json \
  --contamination-length 0.20 \
  --contamination-width 0.07 \
  --contamination-gap 0.05
```

Если `~/scripts/basic_worlds/worlds/clover_aruco.world` отсутствует, можно использовать стандартный путь Clover:

```bash
python3 scripts/generate_world.py \
  --base-world ~/catkin_ws/src/clover/clover_simulation/resources/worlds/clover_aruco.world \
  --output worlds/generated_solar.world \
  --truth-output worlds/generated_truth.json
```

Для демонстрации рандомной генерации не указывайте `--seed`. Скрипт выведет seed и параметры панелей в терминал.

На крайний случай в репозитории уже лежит готовый мир `worlds/generated_solar.world`. Если генерация на конкретной VM не сработала из-за путей Clover или отсутствующего базового world-файла, можно сразу перейти к установке готового мира через `scripts/use_solar_world.sh install`.

`generated_truth.json` создаётся только для отладки и демонстрации генерации. Основная миссия `scripts/inspect_solar.py` его не читает.

## Подмена Мира В Clover

После генерации установить `generated_solar.world` как активный `clover_aruco.world`:

```bash
scripts/use_solar_world.sh install
```

Проверить статус:

```bash
scripts/use_solar_world.sh status
```

Откатить стандартный мир:

```bash
scripts/use_solar_world.sh restore
```

## Запуск Симуляции

Запустите Clover/Gazebo тем launch-файлом, который используется в образе для ArUco-навигации. Например:

```bash
roslaunch clover_simulation simulator.launch
```

Если в вашем образе используется другой launch-файл, используйте его. Важно, чтобы были доступны сервисы:

```bash
rosservice list | grep -E 'navigate|get_telemetry|land'
```

И камера:

```bash
rostopic list | grep -i image
```

Обычно используется топик:

```text
/main_camera/image_raw
```

## Запуск Автономной Миссии

В отдельном терминале:

```bash
cd ~/scripts/Solar_farm_inspection
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash 2>/dev/null || source ~/catkin_ws/install/setup.bash
source .venv/bin/activate
```

Запуск:

```bash
python scripts/inspect_solar.py \
  --image-topic /main_camera/image_raw \
  --model weights/solar_yolov8n_best.pt \
  --output-topic /solar \
  --report reports/solar_report.txt \
  --frame-id map
```

Что происходит во время миссии:

- коптер взлетает;
- облетает 5 точек панелей;
- зависает над каждой панелью около 5 секунд;
- распознаёт панель, загрязнения и цветной индикатор;
- публикует аннотированное изображение в `/solar`;
- включает LED в цвет состояния;
- печатает результат в терминал;
- возвращается к стартовой зоне и садится;
- сохраняет отчёт.

Проверить `/solar`:

```bash
rostopic hz /solar
```

Посмотреть отчёт:

```bash
cat reports/solar_report.txt
```

## Формат Отчёта

Пример:

```text
Solar panel #1: coordinates 0.55 0.55, normal, 3 contaminations
Solar panel #2: coordinates 0.55 5.45, urgent_repair, 4 contaminations
```

В отчёте используется ASCII-текст, чтобы избежать проблем с кодировкой в Clover VM.

## Обученная Модель

Используется `YOLOv8n`, потому что модель лёгкая и достаточно быстрая для VM/CPU.

Файл весов:

```text
weights/solar_yolov8n_best.pt
```

Классы:

```text
contamination
indicator_orange
indicator_red
indicator_yellow
solar_panel
```

Метрики после обучения:

```text
Validation: mAP50 0.967, mAP50-95 0.891
Test:       mAP50 0.949, mAP50-95 0.919
```

## Повторное Обучение

Датасет Roboflow был в формате YOLOv8. Для повторного обучения:

```bash
source .venv/bin/activate
python scripts/train_yolo.py \
  --data dataset/lm/gazeboSolars.v1-gazebosolars.yolov8/data.yaml \
  --model yolov8n.pt \
  --epochs 100 \
  --batch 8 \
  --imgsz 640 \
  --device cpu
```

Лучшие веса появятся в:

```text
runs/detect/solar_yolov8n/weights/best.pt
```

## Демонстрационное Видео

Демонстрационное видео доступно по ссылкам в начале README.

Для зачётного видео по регламенту желательно показать одновременно:

- окно Gazebo с коптером;
- терминал с запуском `scripts/inspect_solar.py`;
- вывод топика `/solar` или просмотр изображения `/solar`;
- содержимое `reports/solar_report.txt`.

## Частые Проблемы

Если солнечные панели не видны, а цветные прямоугольники видны:

```bash
scripts/install_gazebo_models.sh
```

Если Gazebo не находит `parquet_plane` или `aruco_cmit_txt`:

```bash
source scripts/setup_gazebo_env.sh
```

Если `pip install ultralytics` забил диск CUDA-пакетами:

```bash
deactivate 2>/dev/null || true
rm -rf .venv
rm -rf ~/.cache/pip
```

После этого ставьте CPU-only PyTorch, как описано в разделе установки.

Если нет трансформа `aruco_map -> map`, используйте:

```bash
--frame-id map
```

Это значение уже стоит по умолчанию в инструкции запуска.
