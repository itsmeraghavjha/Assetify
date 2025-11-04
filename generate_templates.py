"""
Run this script to generate ALL template files automatically
Usage: python generate_templates.py
"""

import os

# Create directories
os.makedirs('templates/email', exist_ok=True)
os.makedirs('templates/admin', exist_ok=True)

print("Creating template files...")

# ==================== BASE.HTML ====================
base_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Assetify{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .fade-in { animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .thumb { max-width: 100%; height: auto; border-radius: 0.5rem; }
    </style>
</head>
<body class="bg-gray-50">
    <nav class="bg-white shadow-sm border-b border-gray-200">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16">
                <div class="flex items-center">
                    <span class="ml-3 text-xl font-bold text-green-800">Assetify</span>
                    {% if current_user.is_authenticated %}
                    <div class="hidden md:ml-10 md:flex md:space-x-8">
                        <a href="{{ url_for('dashboard') }}" class="inline-flex items-center px-1 pt-1 text-sm font-medium">Dashboard</a>
                        {% if current_user.role in ['SE', 'Admin'] %}
                        <a href="{{ url_for('new_request') }}" class="inline-flex items-center px-1 pt-1 text-sm font-medium">New Request</a>
                        {% endif %}
                        {% if current_user.role == 'Admin' %}
                        <a href="{{ url_for('manage_users') }}" class="inline-flex items-center px-1 pt-1 text-sm font-medium">Manage Users</a>
                        {% endif %}
                    </div>
                    {% endif %}
                </div>
                {% if current_user.is_authenticated %}
                <div class="flex items-center space-x-4">
                    <span class="text-sm">{{ current_user.name }} ({{ current_user.role }})</span>
                    <a href="{{ url_for('logout') }}" class="text-sm text-red-600 hover:text-red-800">Logout</a>
                </div>
                {% endif %}
            </div>
        </div>
    </nav>

    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
        <div class="max-w-7xl mx-auto px-4 mt-4">
            {% for category, message in messages %}
            <div class="rounded p-4 mb-4 {% if category == 'success' %}bg-green-50 text-green-800{% elif category == 'danger' %}bg-red-50 text-red-800{% else %}bg-blue-50 text-blue-800{% endif %}">
                {{ message }}
            </div>
            {% endfor %}
        </div>
        {% endif %}
    {% endwith %}

    <main class="max-w-7xl mx-auto px-4 py-8">
        {% block content %}{% endblock %}
    </main>

    <footer class="bg-white border-t mt-12 py-4">
        <p class="text-center text-sm text-gray-500">&copy; 2025 Heritage Foods</p>
    </footer>
</body>
</html>"""

with open('templates/base.html', 'w', encoding='utf-8') as f:
    f.write(base_html)
print("✓ Created base.html")

# ==================== BASE_FULLSCREEN.HTML ====================
base_fullscreen = """<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Assetify{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="h-full">
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
        <div class="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-md p-4 z-50">
            {% for category, message in messages %}
            <div class="rounded-md shadow-lg p-4 {% if category == 'success' %}bg-green-50 text-green-800{% else %}bg-red-50 text-red-700{% endif %}">
                <p class="text-sm font-medium">{{ message }}</p>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
</body>
</html>"""

with open('templates/base_fullscreen.html', 'w', encoding='utf-8') as f:
    f.write(base_fullscreen)
print("✓ Created base_fullscreen.html")

# ==================== LOGIN.HTML ====================
login_html = """{% extends "base_fullscreen.html" %}
{% block title %}Login{% endblock %}
{% block content %}
<style>
    .login-bg {
        background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
    }
    .glass-card {
        background: rgba(255, 255, 255, 0.6);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
</style>

<div class="min-h-full flex items-center justify-center py-12 px-4 login-bg">
  <div class="max-w-md w-full space-y-8 p-10 glass-card rounded-2xl shadow-2xl">
    <div>
      <h2 class="mt-6 text-center text-3xl font-extrabold text-gray-900">
        Assetify Sign In
      </h2>
      <p class="mt-2 text-center text-sm text-gray-600">Welcome Back</p>
    </div>
    <form class="mt-8 space-y-6" action="{{ url_for('login') }}" method="POST">
      {{ form.hidden_tag() }}
      <div class="space-y-4">
        <div>
          {{ form.employee_code(id="employee-code", placeholder="Employee Code", required=True, class="appearance-none block w-full px-3 py-3 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-green-700 focus:border-green-700") }}
        </div>
        <div>
          {{ form.password(id="password", placeholder="Password", required=True, class="appearance-none block w-full px-3 py-3 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-green-700 focus:border-green-700") }}
        </div>
      </div>

      <div class="flex items-center justify-between">
        <div class="flex items-center">
          {{ form.remember_me(class="h-4 w-4 text-green-700 focus:ring-green-600 border-gray-300 rounded") }}
          {{ form.remember_me.label(class="ml-2 block text-sm text-gray-900") }}
        </div>
      </div>

      <div>
        {{ form.submit(class="w-full flex justify-center py-3 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-green-800 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-700 shadow-lg") }}
      </div>
    </form>
  </div>
</div>
{% endblock %}"""

with open('templates/login.html', 'w', encoding='utf-8') as f:
    f.write(login_html)
print("✓ Created login.html")

# ==================== DASHBOARD.HTML ====================
dashboard_html = """{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<div class="fade-in">
    <div class="flex justify-between mb-6">
        <h1 class="text-3xl font-bold text-gray-900">Dashboard</h1>
        {% if current_user.role in ['SE', 'Admin'] %}
        <a href="{{ url_for('new_request') }}" class="inline-flex items-center px-4 py-2 bg-green-800 text-white rounded-md hover:bg-green-700">
            <i class="fa fa-plus mr-2"></i> New Request
        </a>
        {% endif %}
    </div>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div class="bg-white p-6 rounded-lg shadow">
            <h3 class="text-gray-500 text-sm font-medium">Total Requests</h3>
            <p class="text-2xl font-bold text-gray-900">{{ stats.total_requests }}</p>
        </div>
        <div class="bg-white p-6 rounded-lg shadow">
            <h3 class="text-gray-500 text-sm font-medium">Pending</h3>
            <p class="text-2xl font-bold text-gray-900">{{ stats.pending_requests }}</p>
        </div>
        <div class="bg-white p-6 rounded-lg shadow">
            <h3 class="text-gray-500 text-sm font-medium">Approved</h3>
            <p class="text-2xl font-bold text-gray-900">{{ stats.approved_requests }}</p>
        </div>
        <div class="bg-white p-6 rounded-lg shadow">
            <h3 class="text-gray-500 text-sm font-medium">Rejected</h3>
            <p class="text-2xl font-bold text-gray-900">{{ stats.rejected_requests }}</p>
        </div>
    </div>
    
    <div class="bg-white rounded-lg shadow">
        <div class="p-6 border-b">
            <h2 class="text-xl font-semibold text-gray-800">Recent Requests</h2>
        </div>
        
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Req ID</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                        {% if current_user.role != 'SE' %}<th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Requester</th>{% endif %}
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Distributor</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Asset Model</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                        <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Action</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
                    {% for request in requests %}
                    <tr class="hover:bg-gray-50">
                        <td class="px-6 py-4 text-sm font-medium">#{{ request.id }}</td>
                        <td class="px-6 py-4 text-sm">{{ request.request_date.strftime('%Y-%m-%d') }}</td>
                        {% if current_user.role != 'SE' %}<td class="px-6 py-4 text-sm">{{ request.requester.name }}</td>{% endif %}
                        <td class="px-6 py-4 text-sm">{{ request.distributor.name }}</td>
                        <td class="px-6 py-4 text-sm">{{ request.asset_model }}</td>
                        <td class="px-6 py-4 text-sm">
                            <span class="px-2 py-1 text-xs rounded-full {% if 'Approved' in request.status %}bg-green-100 text-green-800{% elif 'Rejected' in request.status %}bg-red-100 text-red-800{% else %}bg-yellow-100 text-yellow-800{% endif %}">
                                {{ request.status }}
                            </span>
                        </td>
                        <td class="px-6 py-4 text-right text-sm">
                            <a href="{{ url_for('view_request', request_id=request.id) }}" class="text-green-700 hover:text-green-900">View →</a>
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="7" class="text-center py-16 text-gray-500">No requests found.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}"""

with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(dashboard_html)
print("✓ Created dashboard.html")

# I'll continue with the rest in the next message due to length...
print("\n✅ Basic templates created!")
print("Run the app now: flask run")
print("\nNote: You still need to create:")
print("  - new_request.html")
print("  - view_request.html")
print("  - admin/manage_users.html")
print("  - admin/user_form.html")
print("  - email templates")