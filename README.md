<div align="center">
  <h1>✨ AutoMagic Vision ✨</h1>
  <p><strong>A Suite of Next-Gen Hand Tracking and Gesture Control Applications</strong></p>

  <!-- Badges -->
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://opencv.org/"><img src="https://img.shields.io/badge/OpenCV-4.x-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white" alt="OpenCV"></a>
  <a href="https://mediapipe.dev/"><img src="https://img.shields.io/badge/MediaPipe-0.10.x-00B0FF?style=for-the-badge&logo=google&logoColor=white" alt="MediaPipe"></a>
  
  <br><br>
</div>

Welcome to **AutoMagic Vision**, an advanced collection of computer vision tools built using Python, OpenCV, and Google's MediaPipe. This repository transforms your standard webcam into a highly interactive, futuristic controller for games, productivity, and visual effects.

---

## 🚀 Applications Included

This repository contains three standalone applications. You can run any of them independently without configuring the others.

### 1. 🖱️ Smart Mouse Control (`smart_mouse.py`)
Control your PC cursor with the wave of a hand. Perfect for presentations, accessibility, and futuristic setups.
- **Index Finger Tracking**: Move your index finger to smoothly control the mouse cursor. Features adaptive smoothing to eliminate jitter.
- **Pinch-to-Click**: Touch your thumb and index finger together to click.
- **Pinch-to-Drag**: Hold your pinch for 5 seconds to initiate a hold/drag (perfect for moving windows or selecting text).
- **Status HUD**: Real-time on-screen display of finger states, FPS, and gesture actions.

### 2. 🥷 Fruit Ninja: Gesture Edition (`fruit_ninja.py`)
A fully playable, interactive Fruit Ninja clone powered entirely by hand tracking!
- **Hand-Blade**: Your index finger acts as a sword. A dynamic, glowing energy slash follows your movements.
- **Emoji Rendering**: Slices through high-res rendered emojis (🍉, 🍎, 🍊) that physically split in two using advanced image manipulation.
- **Swept-Area Collision**: High-speed, frame-perfect slice detection.
- **Combos & Bombs**: Slice multiple fruits for combo points, and avoid the bombs!

### 3. ✨ Iron Man Magic Effects (`iron_man_magic.py`)
Cinematic augmented reality visual effects applied directly to your hands and face.
- **Repulsor Blasts**: Glowing Iron Man palm repulsors that charge when you pinch.
- **Doctor Strange Portals**: Bring both hands together to create dynamic energy connections, falling sparks, and massive rotating magic portals.
- **Face Tracking Helmet**: Automatically detects your face and overlays an Iron Man HUD with glowing visors and scanning reticles.
- **Electric Arcs**: Procedural lightning bolts jump between your fingertips.

---

## 🛠️ Installation

### Prerequisites
Make sure you have **Python 3.9 - 3.11** installed. *(Note: Python 3.14 is currently not fully supported by some ML dependencies).*

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/AutoMagic-Vision.git
   cd AutoMagic-Vision
   ```

2. **Install Dependencies**
   It is highly recommended to use a virtual environment or Python 3.11.
   ```bash
   pip install opencv-python mediapipe numpy pillow
   ```

3. **MediaPipe Model**
   Ensure `hand_landmarker.task` is located in the root directory. If missing, download it from the [Google MediaPipe Model Hub](https://developers.google.com/mediapipe/solutions/vision/hand_landmarker).

---

## 🎮 Usage

Run the scripts directly from your terminal:

**To start the Mouse Controller:**
```bash
python smart_mouse.py
```
*(Press `C` to enable/disable mouse control, `Q` to quit)*

**To play Fruit Ninja:**
```bash
python fruit_ninja.py
```
*(Press `Q` to quit)*

**To launch Iron Man Magic:**
```bash
python iron_man_magic.py
```
*(Press `E` to toggle effects, `Q` to quit)*

---

## 📸 Screenshots

*(Replace these placeholders with actual screenshots from your app!)*

<div align="center">
  <img src="https://via.placeholder.com/400x250.png?text=Smart+Mouse+Screenshot" alt="Smart Mouse" width="45%">
  <img src="https://via.placeholder.com/400x250.png?text=Fruit+Ninja+Screenshot" alt="Fruit Ninja" width="45%">
</div>

---

## 🧠 Architecture
- **MediaPipe Tasks API**: Utilized for low-latency, robust hand landmark detection.
- **OpenCV (cv2)**: Powers the rendering engine, overlay compositing, and Haar cascade face detection.
- **Pillow (PIL)**: Used in Fruit Ninja to render high-resolution Windows emojis onto transparent Alpha layers for crisp graphics.
- **Win32 API (ctypes)**: Directly interfaces with Windows `SendInput` for zero-latency, absolute mouse positioning and clicking without bloated third-party dependencies.

---

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/yourusername/AutoMagic-Vision/issues).

## 📝 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

<div align="center">
  <p>Made with ❤️ by Kartik</p>
</div>
