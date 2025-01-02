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
│   ├── daily/             # Daily regression and validation tests
│   │   ├── slice_helper.py   # Helper functions for managing slices
│   │   ├── test_iPerf.py     # Tests for iPerf performance
│   │   ├── output/           # Directory for test output files
│   │   ├── __init__.py       # Package initializer for daily tests
│   │   ├── node_tools/       # Utility scripts for node management
│   └── system/            # System-level validation tests
│       ├── test_fpga_slice.py                   # FPGA slice validation
│       ├── test_persistent_storage_slice.py     # Persistent storage slice tests
│       ├── test_l2ptp_slice.py                  # L2 point-to-point slice tests
│       ├── test_l2bridge_slice.py               # L2 bridge slice tests
│       ├── test_l2sts_slice.py                  # L2 stitched slice tests
│       ├── test_nvme_slice.py                   # NVMe slice validation
│       ├── test_fabnet_v6_ext.py                # IPv6 external FABNet tests
│       ├── test_fabnet_v4_ext_renew_slice.py    # IPv4 external FABNet slice renewal
│       ├── test_gpu_slice.py                    # GPU slice validation
│       ├── test_mf_lib_slice.py                 # Managed file library slice tests
│       ├── test_modify_slice.py                 # Slice modification tests
│       ├── test_l3rt_slice.py                   # L3 route slice validation
│       ├── test_al2s_slice.py                   # AL2S slice validation
│       └── gpu_files/                           # Supporting files for GPU tests
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

## Contact
For questions or contributions, please contact:
**Komal Thareja**  
Email: [your.email@example.com](mailto:your.email@example.com)  
GitHub: [yourusername](https://github.com/yourusername)

