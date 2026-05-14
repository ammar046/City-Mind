# City-Mind: Urban AI Simulation & Optimization

A comprehensive AI-powered city simulation system that combines multiple optimization algorithms and machine learning techniques to solve complex urban planning and emergency response challenges.

## 📋 Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
- [Challenges & Algorithms](#challenges--algorithms)
- [System Architecture](#system-architecture)
- [Configuration](#configuration)
- [Controls & Interface](#controls--interface)
- [Dependencies](#dependencies)

## 🌆 Overview

City-Mind is an AI simulation system that addresses five core urban management challenges:

1. **City Layout Planning** - Optimal placement of urban infrastructure using Constraint Satisfaction Problems (CSP)
2. **Road Network Design** - Building efficient road networks connecting key facilities
3. **Crime Prediction** - Machine learning-based crime risk assessment
4. **Emergency Response** - Genetic algorithm optimization for ambulance routing
5. **Emergency Navigation** - A* pathfinding for dynamic urban environments with obstacles

The system includes a full Pygame-based visualization with isometric 3D map rendering, real-time event logging, and interactive controls.

## ✨ Features

- **Multi-Algorithm Integration**: CSP, Genetic Algorithms, A* Pathfinding, ML-based crime prediction
- **Dynamic Urban Events**: Real-time flood simulation affecting road networks
- **Rich Visualization**: 
  - Isometric 3D city map
  - Flat map toggle
  - Multiple tabs (Map, Heatmaps, Event Log, Ambulance tracking)
  - Real-time heatmaps for crime risk and ambulance response
- **Interactive Controls**: Play/pause, step-by-step execution, speed control
- **Event Logging**: Complete record of all simulation events
- **Graph-Based City Model**: Flexible node-edge representation for infrastructure

## 📁 Project Structure

```
citymind/
├── main.py              # Entry point - Pygame initialization
├── ui.py                # Pygame UI, rendering, interactive controls
├── simulation.py        # Simulation engine orchestrating all challenges
├── graph.py             # City graph model (nodes, edges, infrastructure)
├── challenge1.py        # CSP Layout & city planning
├── challenge2.py        # Road network builder
├── challenge3.py        # Crime risk ML prediction
├── challenge4.py        # Genetic algorithm ambulance routing
├── challenge5.py        # A* dynamic routing with flood obstacles
├── pyrightconfig.json   # Pyright static analysis config
└── README.md            # This file
```

## 🚀 Installation

### Prerequisites
- Python 3.8+
- pip (Python package manager)

### Step 1: Clone the Repository
```bash
git clone https://github.com/ammar046/City-Mind.git
cd City-Mind
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

Or manually install required packages:
```bash
pip install pygame numpy scikit-learn
```

### Step 3: Verify Installation
```bash
python citymind/main.py
```

The Pygame window should open with a city simulation running.

## 💻 Usage

### Running the Simulation

**Basic startup:**
```bash
python citymind/main.py
```

**From project root:**
```bash
cd citymind
python main.py
```

### Interactive Controls

| Key | Action |
|-----|--------|
| **SPACE** | Play/Pause simulation |
| **→** | Step forward one frame |
| **←** | Step backward one frame |
| **+/-** | Increase/Decrease simulation speed |
| **M** | Toggle between isometric and flat map views |
| **Tab** | Cycle through display tabs (Map, Heatmaps, Events, Ambulance) |
| **H** | Toggle heatmap overlay |
| **ESC** | Exit simulation |

### Simulation Phases

The simulation runs in strict order:

1. **Layout Phase** - CSP solver places residential, hospital, school, industrial, power plant facilities
2. **Road Phase** - Road builder connects critical infrastructure
3. **Crime Phase** - ML model calculates crime risk for each residential area
4. **Ambulance Phase** - Genetic algorithm optimizes ambulance deployment and routes
5. **Routing Phase** - A* pathfinder handles emergency navigation with dynamic obstacles (floods)

Each phase is integrated into the main simulation loop (50 steps by default).

## 🧠 Challenges & Algorithms

### Challenge 1: City Layout (CSP)
**File:** `challenge1.py`

Uses Constraint Satisfaction Problem solving to optimally place urban facilities:
- Residential zones near schools and away from industrial areas
- Hospitals positioned for maximum coverage
- Industrial zones with pollution containment
- Validates complete road network connectivity

**Key Functions:**
- `CSPLayout.solve()` - Finds optimal facility placement
- `validate_built_road_network()` - Ensures network integrity

---

### Challenge 2: Road Network Builder
**File:** `challenge2.py`

Constructs efficient road networks connecting key infrastructure:
- Creates primary roads between critical nodes
- Implements road-building algorithms
- Optimizes connectivity and reduces travel distances

**Key Functions:**
- `RoadBuilder.build()` - Generates road network

---

### Challenge 3: Crime Risk Prediction (ML)
**File:** `challenge3.py`

Machine learning model that predicts crime risk:
- Features: proximity to schools, hospitals, industrial zones
- ML model: Trained predictor (likely scikit-learn)
- Output: Crime risk heatmap for each location

**Key Functions:**
- `CrimeRisk.predict()` - Generate crime risk scores
- `CrimeRisk.train()` - Train the ML model

---

### Challenge 4: Ambulance Routing (Genetic Algorithm)
**File:** `challenge4.py`

Optimizes emergency ambulance deployment using genetic algorithms:
- Genome: Ambulance locations and routes
- Fitness: Response time to emergency calls
- Evolution: Iterative improvement over generations
- Dynamic: Adapts to real-time emergency patterns

**Key Functions:**
- `GeneticAmbulance.evolve()` - Run GA iterations
- `GeneticAmbulance.get_best_solution()` - Get optimal ambulance placement

---

### Challenge 5: Emergency Navigation (A*)
**File:** `challenge5.py`

A* pathfinding algorithm for dynamic urban navigation:
- Static obstacles: Buildings, non-road terrain
- Dynamic obstacles: Floods that block roads temporarily
- Optimization: Finds shortest path considering heuristics
- Robustness: Handles unreachable scenarios

**Key Functions:**
- `AStarRouter.find_path()` - Compute path from A to B
- `AStarRouter.handle_obstacles()` - Process dynamic obstacles

---

## 🏗 System Architecture

### Graph Model (`graph.py`)
- **Node Types**: `residential`, `hospital`, `school`, `industrial`, `powerplant`, `depot`, `empty`
- **CityGraph Class**: Manages 8×8 grid city with ~64 nodes
- **Edge Representation**: Roads connecting adjacent or strategic nodes

### Simulation Engine (`simulation.py`)
- **Orchestration**: Coordinates all 5 challenges in sequence
- **Event Loop**: Stepped simulation (one `nextstep()` = one tick)
- **Flood System**: Real-time wall-clock timers for dynamic obstacles
- **State Management**: Tracks step count, events, ambulance positions

### UI System (`ui.py`)
- **Rendering**: Isometric 3D projection + flat map mode
- **Threading**: Runs simulation in separate thread for responsive UI
- **Tabs**: Map, Heatmaps, Event Log, Ambulance Tracking
- **Colors**: 16+ custom colors for different UI elements

---

## ⚙ Configuration

Edit these values in `simulation.py` to customize:

```python
gridrows = 8                          # Grid height
gridcols = 8                          # Grid width
numsteps = 50                         # Simulation duration (steps)
flood_duration_min_s = 4.0            # Min flood block time (seconds)
flood_duration_max_s = 4.0            # Max flood block time (seconds)
router_nearest_first = False          # Ambulance routing strategy
```

## 🎮 Interface Guide

### Tabs (Press Tab to cycle)

1. **Map Tab**: Main isometric/flat city view with facilities and roads
2. **Heatmaps Tab**: Visualization of crime risk across city
3. **Event Log Tab**: Scrollable log of all simulation events
4. **Ambulance Tab**: Real-time ambulance positions and routing

### Display Elements

- **Color Legend**: Node types have distinct colors
- **Road Network**: Blue lines showing connectivity
- **Floods**: Red zones indicating blocked areas
- **Ambulances**: Icon showing current position and route

## 📦 Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pygame` | 2.x+ | Game engine & visualization |
| `numpy` | 1.x+ | Numerical computing, array operations |
| `scikit-learn` | 1.x+ | Machine learning (crime prediction) |

Install all at once:
```bash
pip install pygame numpy scikit-learn
```

## 🔧 Troubleshooting

### Issue: ImportError for pygame
**Solution:**
```bash
pip install --upgrade pygame
```

### Issue: Slow simulation
**Solution:**
- Reduce `numsteps` in `simulation.py`
- Lower window resolution (check `ui.py` screen dimensions)
- Use faster routing options

### Issue: Floods not appearing
**Verify** in `simulation.py`:
- `flood_duration_min_s` and `flood_duration_max_s` are > 0
- `expire_floods()` is called each UI frame

---

## 📊 Performance Notes

- **8×8 Grid**: ~64 nodes, suitable for real-time visualization
- **A* Pathfinding**: O(b^d) where b=branching factor, d=depth
- **Genetic Algorithm**: Configurable generations (default ~50)
- **ML Prediction**: Fast inference using scikit-learn

---

## 🤝 Contributing

To extend City-Mind:

1. **Add new challenges** - Create `challengeN.py` following the pattern
2. **Enhance UI** - Modify `ui.py` for new visualizations
3. **Expand graph** - Extend `graph.py` for more infrastructure types
4. **Tune algorithms** - Adjust parameters in respective challenge files

---

## 📝 License

This project is part of an AI course/challenge series.

---

## 🎯 Quick Start Summary

```bash
# Clone and navigate
git clone https://github.com/ammar046/City-Mind.git
cd City-Mind

# Install dependencies
pip install pygame numpy scikit-learn

# Run simulation
python citymind/main.py

# Press SPACE to start, Tab to switch views, ESC to exit
```

**Enjoy exploring urban AI optimization! 🌆**
