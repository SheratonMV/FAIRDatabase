# CLAUDE.md - Frontend Development Guide

This file provides comprehensive frontend-specific guidance for the FAIRDatabase project. It extends the root CLAUDE.md with frontend-specific conventions and standards.

## 📋 Frontend Overview

The FAIRDatabase frontend currently uses server-side templates with Flask/Jinja2. The frontend is organized into:
- **frontend/templates/**: Jinja2 HTML templates organized by feature
- **frontend/public/**: Logo images only (avatar1.png, metahealth_logo.svg, metahealth_small.png)
- **static/**: Static assets at ROOT level (CSS, JavaScript, images)

**IMPORTANT**: Main static assets (CSS, JS, images) are in `/static/` at the ROOT level, NOT in `frontend/public/`

## 🎨 Current Technology Stack

### Template Engine
- **Jinja2**: Server-side templating with Flask
- Templates inherit from base layouts
- Dynamic content rendered server-side

### Frontend Assets
- **CSS**: Main stylesheet at `/static/styles.css`
- **JavaScript**: Main script at `/static/script.js`
- **Images**: Located in `/static/img/`
- **No Build Process**: No webpack, vite, or bundler (yet)
- **No Framework**: Vanilla JavaScript only

## 🏗️ Directory Structure

```
frontend/
├── CLAUDE.md          # This file
├── public/            # Logo images ONLY
│   ├── avatar1.png
│   ├── metahealth_logo.svg
│   └── metahealth_small.png
└── templates/         # Jinja2 templates
    ├── auth/         # Authentication pages
    ├── dashboard/    # Dashboard views
    ├── data/         # Data management views
    ├── documentation/# Documentation pages
    ├── federated_learning/
    └── privacy/      # Privacy-related pages

static/                # Static assets (at ROOT level, not in frontend/)
├── styles.css        # Main stylesheet
├── script.js         # Main JavaScript
└── img/              # Image assets
    ├── avatar1.png
    ├── metahealth_logo.svg
    └── metahealth_small.png
```

## 🔧 Development Guidelines

### Template Best Practices
1. **Template Inheritance**: Always extend from base templates
2. **Blocks**: Use semantic block names (content, scripts, styles)
3. **Macros**: Create reusable components as Jinja2 macros
4. **Escaping**: Always escape user input with `{{ variable|e }}`

### CSS Organization
- Use BEM naming convention for classes
- Keep component styles isolated
- Mobile-first responsive design
- Minimize use of !important

### JavaScript Guidelines
- Progressive enhancement approach
- No inline JavaScript in templates
- Use data attributes for configuration
- Handle errors gracefully

## 🚀 Future Migration Path

### Planned Improvements
The frontend is scheduled for modernization:
1. **Phase 1**: Improve current template structure
2. **Phase 2**: Add build tooling (webpack/vite)
3. **Phase 3**: Introduce component framework (Vue/React/Svelte)
4. **Phase 4**: API-first architecture with SPA

### Migration Priorities
- Maintain backward compatibility during transition
- Preserve all existing functionality
- Improve accessibility (WCAG 2.1 AA)
- Enhance performance metrics

## 🔒 Security Considerations

### Template Security
- **XSS Prevention**: Always escape user input with `{{ variable|e }}` or rely on Jinja2's autoescaping
- **CSRF Protection**: Use Flask's session-based CSRF protection
- **Content Security Policy**: Implement CSP headers
- **Input Validation**: Validate on both client and server (server-side uses custom handler classes)

### Asset Security
- Serve static files through Flask in development
- Use CDN with SRI hashes for external resources
- Minify and obfuscate JavaScript in production
- Implement rate limiting on API endpoints

## 📝 Form Handling

**IMPORTANT**: This project uses **custom handler classes** (NOT Flask-WTF or Pydantic)

### Form Guidelines
```jinja2
{# Simple HTML forms - backend uses custom handler classes #}
<form method="POST" action="{{ url_for('route_name') }}">
    <div class="form-group">
        <label for="email">Email</label>
        <input type="email"
               id="email"
               name="email"
               class="form-control"
               required>
    </div>

    <div class="form-group">
        <label for="password">Password</label>
        <input type="password"
               id="password"
               name="password"
               class="form-control"
               required>
    </div>

    <button type="submit" class="btn btn-primary">Submit</button>
</form>

{# Flash messages for validation errors #}
{% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
        {% for category, message in messages %}
            <div class="alert alert-{{ category }}">
                {{ message }}
            </div>
        {% endfor %}
    {% endif %}
{% endwith %}
```

### Backend Form Processing
Forms are processed server-side using custom handler classes:
- `LoginHandler`, `RegisterHandler` in `backend/src/auth/form.py`
- `BaseHandler` in `backend/src/form_handler.py`
- Handlers extract data from `request.form`
- Validation errors sent back via `flash()` messages
- See `backend/CLAUDE.md` for handler class details

## 🎯 Component Patterns

### Reusable Macros
Create macros for common UI patterns:
```jinja2
{% macro render_input_field(name, label, type="text", required=true) %}
    <div class="form-group">
        <label for="{{ name }}">{{ label }}</label>
        <input type="{{ type }}"
               id="{{ name }}"
               name="{{ name }}"
               class="form-control"
               {% if required %}required{% endif %}>
    </div>
{% endmacro %}

{# Usage #}
{{ render_input_field("email", "Email Address", type="email") }}
{{ render_input_field("password", "Password", type="password") }}
```

### Flash Messages
Consistent flash message handling:
```jinja2
{% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
        {% for category, message in messages %}
            <div class="alert alert-{{ category }}">
                {{ message }}
            </div>
        {% endfor %}
    {% endif %}
{% endwith %}
```

## 🧪 Testing Frontend

### Visual Testing
- Test responsive layouts at key breakpoints
- Verify cross-browser compatibility
- Check accessibility with screen readers
- Validate HTML/CSS with W3C validators

### Integration Testing
- Test form submissions and validation
- Verify error handling and messages
- Check authentication flows
- Test data display and pagination

## 📊 Performance Guidelines

### Optimization Checklist
- [ ] Minimize HTTP requests
- [ ] Optimize images (WebP format)
- [ ] Lazy load below-the-fold content
- [ ] Use browser caching effectively
- [ ] Minimize CSS/JS bundle sizes
- [ ] Enable gzip compression

## 🔍 Debugging Tips

### Browser DevTools
- Use Network tab to monitor requests
- Check Console for JavaScript errors
- Inspect elements for CSS issues
- Monitor performance metrics

### Flask Debug Mode
- Enable Flask debug mode in development
- Use Flask Debug Toolbar for insights
- Check template rendering context
- Monitor database queries

## 📚 Resources

### Documentation
- [Jinja2 Documentation](https://jinja.palletsprojects.com/)
- [Flask Templates Guide](https://flask.palletsprojects.com/en/stable/tutorial/templates/)
- [Bootstrap Documentation](https://getbootstrap.com/docs/)

### Tools
- Browser DevTools (Chrome/Firefox)
- Lighthouse for performance audits
- WAVE for accessibility testing
- PostCSS for CSS processing

## ⚠️ Current Issues

### Known Limitations
1. No frontend build process currently
2. Limited JavaScript organization
3. Styles not modularized
4. No automated testing for UI

### Priority Fixes
1. Implement CSS preprocessing
2. Add JavaScript bundling
3. Improve form validation UX
4. Enhance mobile responsiveness

---

**Note**: This document will evolve as the frontend architecture is modernized. Always check for updates when starting new frontend work.