#!/usr/bin/env python3
"""
Setup script for Oracle SQL Assistant - AWS Bedrock Enhanced Edition
This script helps configure the enhanced system with proper dependencies and environment setup.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
import json

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Error: Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True

def check_aws_cli():
    """Check if AWS CLI is available"""
    try:
        result = subprocess.run(['aws', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ AWS CLI: {result.stdout.strip()}")
            return True
        else:
            print("⚠️ AWS CLI not found - you'll need to configure AWS credentials manually")
            return False
    except FileNotFoundError:
        print("⚠️ AWS CLI not found - you'll need to configure AWS credentials manually")
        return False

def create_virtual_environment():
    """Create virtual environment"""
    venv_path = Path("app_env")
    
    if venv_path.exists():
        print("✅ Virtual environment already exists")
        return True
    
    try:
        print("🔧 Creating virtual environment...")
        subprocess.run([sys.executable, '-m', 'venv', 'app_env'], check=True)
        print("✅ Virtual environment created successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create virtual environment: {e}")
        return False

def install_dependencies():
    """Install Python dependencies"""
    print("🔧 Installing dependencies...")
    
    # Determine the correct pip path based on OS
    if os.name == 'nt':  # Windows
        pip_path = Path("app_env/Scripts/pip.exe")
    else:  # Unix-like
        pip_path = Path("app_env/bin/pip")
    
    if not pip_path.exists():
        print("❌ Virtual environment pip not found")
        return False
    
    try:
        # Upgrade pip first
        subprocess.run([str(pip_path), 'install', '--upgrade', 'pip'], check=True)
        
        # Install requirements
        subprocess.run([str(pip_path), 'install', '-r', 'requirements.txt'], check=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def setup_environment_file():
    """Setup environment configuration file"""
    env_file = Path(".env")
    env_template = Path("env_template.txt")
    
    if env_file.exists():
        print("✅ .env file already exists")
        return True
    
    if not env_template.exists():
        print("❌ Environment template not found")
        return False
    
    try:
        shutil.copy(env_template, env_file)
        print("✅ Environment file created from template")
        print("⚠️ Please edit .env file with your actual credentials")
        return True
    except Exception as e:
        print(f"❌ Failed to create environment file: {e}")
        return False

def copy_original_system_files():
    """Copy necessary files from original system"""
    original_path = Path("../sql-generation-oracle-fusion")
    
    if not original_path.exists():
        print("⚠️ Original system not found - some features may not be available")
        return False
    
    files_to_copy = [
        "sqlgen.py",
        "sqlgen_pinecone.py", 
        "excel_generator.py",
        "bip_automator.py",
        "bip_upload.py",
        "chroma_db"
    ]
    
    copied_files = []
    for file_name in files_to_copy:
        src = original_path / file_name
        dst = Path(file_name)
        
        if src.exists():
            try:
                if src.is_dir():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                copied_files.append(file_name)
                print(f"✅ Copied {file_name}")
            except Exception as e:
                print(f"⚠️ Failed to copy {file_name}: {e}")
        else:
            print(f"⚠️ {file_name} not found in original system")
    
    if copied_files:
        print(f"✅ Copied {len(copied_files)} files from original system")
        return True
    else:
        print("⚠️ No files copied from original system")
        return False

def test_bedrock_connection():
    """Test AWS Bedrock connection"""
    print("🔧 Testing AWS Bedrock connection...")
    
    try:
        # Import and test Bedrock client
        sys.path.insert(0, str(Path.cwd()))
        from bedrock_integration import create_bedrock_client
        
        client = create_bedrock_client()
        models = client.get_available_models()
        
        if models:
            print("✅ AWS Bedrock connection successful")
            print(f"Available models: {', '.join(models)}")
            return True
        else:
            print("⚠️ AWS Bedrock connected but no models found")
            return False
            
    except Exception as e:
        print(f"❌ AWS Bedrock connection failed: {e}")
        print("Please check your AWS credentials and Bedrock access")
        return False

def create_startup_script():
    """Create startup script"""
    if os.name == 'nt':  # Windows
        script_content = """@echo off
echo Starting Oracle SQL Assistant - AWS Bedrock Enhanced Edition
echo.
call app_env\\Scripts\\activate
python app_enhanced.py
pause
"""
        script_path = "start_enhanced.bat"
    else:  # Unix-like
        script_content = """#!/bin/bash
echo "Starting Oracle SQL Assistant - AWS Bedrock Enhanced Edition"
echo ""
source app_env/bin/activate
python app_enhanced.py
"""
        script_path = "start_enhanced.sh"
    
    try:
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        if os.name != 'nt':  # Make executable on Unix-like systems
            os.chmod(script_path, 0o755)
        
        print(f"✅ Startup script created: {script_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to create startup script: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 Oracle SQL Assistant - AWS Bedrock Enhanced Edition Setup")
    print("=" * 60)
    
    # Check prerequisites
    if not check_python_version():
        return False
    
    check_aws_cli()
    
    # Setup steps
    steps = [
        ("Creating virtual environment", create_virtual_environment),
        ("Installing dependencies", install_dependencies),
        ("Setting up environment file", setup_environment_file),
        ("Copying original system files", copy_original_system_files),
        ("Creating startup script", create_startup_script),
    ]
    
    for step_name, step_func in steps:
        print(f"\n📋 {step_name}...")
        if not step_func():
            print(f"❌ Setup failed at: {step_name}")
            return False
    
    # Test Bedrock connection (optional)
    print(f"\n📋 Testing AWS Bedrock connection...")
    test_bedrock_connection()
    
    print("\n" + "=" * 60)
    print("🎉 Setup completed successfully!")
    print("\n📝 Next steps:")
    print("1. Edit .env file with your AWS credentials and API keys")
    print("2. Ensure AWS Bedrock is enabled in your AWS account")
    print("3. Run the application:")
    if os.name == 'nt':
        print("   - Windows: double-click start_enhanced.bat")
    else:
        print("   - Unix/Linux: ./start_enhanced.sh")
    print("4. Open your browser to http://localhost:7860")
    print("5. Test the /diagnose endpoint to verify configuration")
    
    print("\n🔧 Configuration files:")
    print("- .env: Environment variables and API keys")
    print("- app_enhanced.py: Enhanced Flask application")
    print("- bedrock_integration.py: AWS Bedrock integration")
    
    print("\n📚 Documentation:")
    print("- README.md: Complete documentation")
    print("- env_template.txt: Environment configuration template")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
