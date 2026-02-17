#!/usr/bin/env python3
"""
Setup verification script for Personal Life OS
Run this to check if everything is configured correctly
"""
import sys

def check_python_version():
    """Check if Python version is 3.9+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print("❌ Python 3.9+ is required")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_dependencies():
    """Check if all required packages are installed"""
    required = [
        "streamlit",
        "supabase",
        "telegram",
        "anthropic",
        "pydantic",
        "pandas",
        "plotly",
        "dotenv"
    ]
    
    missing = []
    for package in required:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} not found")
            missing.append(package)
    
    if missing:
        print("\n⚠️  Install missing packages with:")
        print("pip install -r requirements.txt")
        return False
    
    return True


def check_env_file():
    """Check if .env file exists and has required variables"""
    import os
    from pathlib import Path
    
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env file not found")
        print("   Create one by copying .env.example:")
        print("   cp .env.example .env")
        return False
    
    print("✅ .env file exists")
    
    # Load and check variables
    from dotenv import load_dotenv
    load_dotenv()
    
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "TELEGRAM_BOT_TOKEN",
        "ANTHROPIC_API_KEY"
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            print(f"   ❌ {var} not set")
            missing.append(var)
        else:
            print(f"   ✅ {var} is set")
    
    if missing:
        print("\n⚠️  Please set the missing environment variables in .env")
        return False
    
    return True


def test_supabase_connection():
    """Test connection to Supabase"""
    try:
        from database import Database
        db = Database()
        print("✅ Supabase connection successful")
        return True
    except Exception as e:
        print(f"❌ Supabase connection failed: {str(e)}")
        return False


def test_anthropic_connection():
    """Test connection to Anthropic API"""
    try:
        from claude_client import get_claude_client
        client = get_claude_client()
        print("✅ Anthropic API client initialized")
        return True
    except Exception as e:
        print(f"❌ Anthropic API connection failed: {str(e)}")
        return False


def main():
    """Run all checks"""
    print("🔍 Personal Life OS - Setup Verification\n")
    print("=" * 50)
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Environment Variables", check_env_file),
        ("Supabase Connection", test_supabase_connection),
        ("Anthropic API", test_anthropic_connection),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n{name}:")
        print("-" * 50)
        results.append(check_func())
    
    print("\n" + "=" * 50)
    
    if all(results):
        print("\n✅ All checks passed! You're ready to go!")
        print("\nNext steps:")
        print("1. Start the bot: python bot.py")
        print("2. Start the dashboard: streamlit run app.py")
    else:
        print("\n❌ Some checks failed. Please fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
