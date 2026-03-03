app_name = "prisma_assistant"
app_title = "Prisma Assistant"
app_publisher = "Prisma Technology"
app_description = "Prisma AI Assistant — general-purpose AI chat for ERPNext"
app_email = "admin@prismatechnology.com"
app_license = "mit"

app_include_js = [
	"/assets/prisma_assistant/js/desk_widget.js",
	"/assets/prisma_assistant/js/title_override.js",
]
app_include_css = ["/assets/prisma_assistant/css/desk_widget.css"]

# Installation
# ------------

after_install = "prisma_assistant.install.after_install"
after_migrate = "prisma_assistant.install.after_migrate"
