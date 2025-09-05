#!/bin/bash

# Fast.BI DBT Runner - PyPI Upload Script
# This script builds and uploads the package to PyPI

set -e  # Exit on any error

echo "🚀 Fast.BI DBT Runner - PyPI Upload Script"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "setup.py" ]; then
    print_error "setup.py not found. Please run this script from the package root directory."
    exit 1
fi

# Check if required tools are installed
print_status "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed or not in PATH"
    exit 1
fi

if ! command -v pip &> /dev/null; then
    print_error "pip is not installed or not in PATH"
    exit 1
fi

print_success "Prerequisites check passed"

# Clean previous builds
print_status "Cleaning previous builds..."
rm -rf build/ dist/ *.egg-info/
print_success "Cleanup completed"

# Install/upgrade build tools
print_status "Installing/upgrading build tools..."
pip install --upgrade setuptools wheel twine
print_success "Build tools ready"

# Check package structure
print_status "Validating package structure..."
if [ ! -f "README.md" ]; then
    print_error "README.md not found"
    exit 1
fi

if [ ! -f "LICENSE" ]; then
    print_error "LICENSE not found"
    exit 1
fi

if [ ! -f "CHANGELOG.md" ]; then
    print_error "CHANGELOG.md not found"
    exit 1
fi

print_success "Package structure validation passed"

# Build the package
print_status "Building package..."
python3 setup.py sdist bdist_wheel
print_success "Package built successfully"

# Check the built package
print_status "Checking built package..."
twine check dist/*
print_success "Package validation passed"

# Show package info
print_status "Package information:"
ls -la dist/

# Ask for confirmation before upload
echo
print_warning "Ready to upload to PyPI"
echo "Package will be uploaded as: fast-bi-dbt-runner"
echo
read -p "Do you want to proceed with the upload? (y/N): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Uploading to PyPI..."
    
    # Check if TWINE_USERNAME and TWINE_PASSWORD are set
    if [ -z "$TWINE_USERNAME" ] || [ -z "$TWINE_PASSWORD" ]; then
        print_warning "TWINE_USERNAME and/or TWINE_PASSWORD not set"
        print_status "You will be prompted for credentials"
    fi
    
    # Upload to PyPI
    twine upload dist/*
    
    print_success "Package uploaded successfully to PyPI!"
    echo
    print_status "Package URL: https://pypi.org/project/fast-bi-dbt-runner/"
    print_status "Documentation: https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration"
else
    print_warning "Upload cancelled"
    print_status "Package files are available in the dist/ directory"
fi

echo
print_success "Script completed successfully!"
