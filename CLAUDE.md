# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Test Commands
- Start backend server: `cd backend && npm start`
- Run Python tests: `cd tests/python && pytest test_*.py`
- Run single Python test: `cd tests/python && pytest test_gemma_data_preprocessor.py::test_initialization`
- Run JavaScript tests: `cd tests/javascript && jest test_*.js`
- Run single JavaScript test: `cd tests/javascript && jest test_frontend.js --testNamePattern="renderElement"`
- Install Python dependencies: `pip install -r python/requirements.txt`

## Code Style Guidelines
- **JavaScript**: Check JS with defaults (allowJs: true, checkJs: false)
- **Python**: Use pytest for testing, PEP 8 style conventions
- **Error Handling**: Use try/except blocks in Python, try/catch in JavaScript
- **Imports**: Group standard library imports first, then third-party, then local
- **Naming**: Use camelCase for JS variables/functions, snake_case for Python
- **Type Annotations**: Optional for Python, use dataclasses and typing-extensions
- **3D Visualization**: Uses Three.js for signal/drone visualization and Cesium for maps
- **WebSocket**: Primary communication method between frontend and backend