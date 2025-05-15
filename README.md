# Fabric System Tests
Fabric System and CI tests

## Overview
The `fabric-system-tests` repository contains automated test scripts for validating the functionality and performance of the FABRIC testbed. These tests are designed to run daily and systematically to ensure the stability and reliability of the system.

## Directory Structure
```
fabric-system-tests/
├── tests/
│   ├── base_test.py       # Base class for common test utilities
│   ├── __init__.py        # Package initializer
│   ├── acceptance/        # Acceptance Tests to validate Sites after release upgrade   
│   ├── daily/             # Daily Regression Test
│   └── system/            # System-level validation tests to validate new features

```

## Getting Started

### Prerequisites
- Python 3.8 or higher
- Required Python packages (install using `pip install -r requirements.txt`)
- Access to the FABRIC environment
  - [Jupyter Hub environment](https://learn.fabric-testbed.net/article-categories/jupyter-hub/)
  - [Local FABRIC API environment](https://learn.fabric-testbed.net/knowledge-base/install-the-python-api/) 

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/fabric-system-tests.git
   cd fabric-system-tests
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running Tests

NOTE: Running tests locally, update `DEBUG=TRUE` and `fabric_rc` to point to the correct path in `tests/base_test.py` accordingly.

#### Acceptance Tests
Run the daily tests located in the `tests/acceptance/` directory:
```bash
pytest tests/acceptance
```

#### Daily Tests
Run the daily tests located in the `tests/daily/` directory:
```bash
pytest tests/daily
```

#### System Tests
Run the system-level tests located in the `tests/system/` directory:
```bash
pytest tests/system
```

#### Specific Test
To run a specific test script, specify its path:
```bash
pytest tests/system/test_fpga_slice.py
```

### Test Output
- Test results are logged to the `output/` directory within the respective test folder.
- Logs and detailed reports are available for debugging and analysis.

## Contributing
1. Fork the repository.
2. Create a feature branch:
   ```bash
   git checkout -b feature-branch
   ```
3. Commit your changes:
   ```bash
   git commit -m "Add a meaningful commit message"
   ```
4. Push to the branch:
   ```bash
   git push origin feature-branch
   ```
5. Create a pull request.

## License
This project is licensed under the MIT License. See the `LICENSE` file for details.

