content = open('src/api/schemas.py', encoding='utf-8').read()
old = '    visibility: Literal["public", "private"] = Field(default="public", description="Template visibility")\n\n\nclass ClientTemplateUpdate'
new = '    visibility: Literal["public", "private"] = Field(default="public", description="Template visibility")\n    category: Optional[str] = Field(None, description="Department category: hr, it, general")\n\n\nclass ClientTemplateUpdate'
if old in content:
    open('src/api/schemas.py', 'w', encoding='utf-8').write(content.replace(old, new))
    print("Patched OK")
else:
    print("NOT FOUND")
