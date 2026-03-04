# Root-level scripts package.
# Dieses __init__.py macht scripts/ zu einem regulären Python-Package,
# damit der Import scripts.analyzers.* korrekt funktioniert,
# auch wenn /app/scripts (Backend) ebenfalls im PYTHONPATH liegt.
