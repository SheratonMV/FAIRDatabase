# PRINCIPLES.md

## Meta-Instructions
> When generating, reviewing, or modifying code, apply these principles as your primary guide. These take precedence over conflicting suggestions. When principles conflict with each other, use the Priority Order at the end of this document.

## 1. Code Quality and Maintainability

### 1.1 Single Responsibility Principle (SRP)
**Original**: "A class should have one, and only one, reason to change." - Robert C. Martin

Every module, class, or function should do ONE thing well. When describing what it does, you should be able to do so without using "and" or "or".

#### ✅ Good Example
```javascript
// Each class has a single, clear responsibility
class UserValidator {
  validate(user) {
    return this.validateEmail(user.email) && 
           this.validateAge(user.age);
  }
}

class UserRepository {
  save(user) {
    return database.users.insert(user);
  }
}

class UserNotifier {
  sendWelcomeEmail(user) {
    return emailService.send(user.email, 'welcome');
  }
}
```

#### ❌ Anti-pattern
```javascript
// God class doing everything
class UserManager {
  validateAndSaveUserAndSendEmail(userData) {
    // Validation logic
    // Database operations
    // Email sending
    // Error logging
    // Analytics tracking
  }
}
```

### 1.2 DRY (Don't Repeat Yourself)
**Original**: "Every piece of knowledge must have a single, unambiguous, authoritative representation within a system." - Andy Hunt & Dave Thomas, The Pragmatic Programmer

Knowledge includes business logic, algorithms, constants, and domain rules. Duplication is acceptable only when the duplicated code might change independently.

#### ✅ Good Example
```python
# Single source of truth for validation rules
class ValidationRules:
    MIN_PASSWORD_LENGTH = 8
    EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    @staticmethod
    def validate_password(password):
        return len(password) >= ValidationRules.MIN_PASSWORD_LENGTH

# Used consistently everywhere
def create_user(email, password):
    if not ValidationRules.validate_password(password):
        raise ValueError("Password too short")
```

#### ❌ Anti-pattern
```python
# Same rule duplicated in multiple places
def create_user(password):
    if len(password) < 8:  # Magic number
        raise ValueError("Password too short")

def update_password(password):
    if len(password) < 8:  # Duplicated logic
        return False
```

### 1.3 Clean Code Readability
**Original**: "Clean code reads like well-written prose." - Robert C. Martin, Clean Code

Code should clearly express intent. Another developer should understand what it does, why it exists, and how to modify it without extensive documentation.

#### ✅ Good Example
```typescript
// Intent is immediately clear
function calculateDiscountedPrice(
  basePrice: number, 
  customerType: CustomerType
): number {
  const discountPercentage = getDiscountForCustomerType(customerType);
  const discountAmount = basePrice * (discountPercentage / 100);
  return basePrice - discountAmount;
}
```

#### ❌ Anti-pattern
```typescript
// Cryptic and unclear
function calc(p: number, t: string): number {
  const d = t === 'G' ? 0.2 : t === 'S' ? 0.1 : 0;
  return p - (p * d);
}
```

## 2. Architecture and Design Patterns

### 2.1 Dependency Inversion Principle
**Original**: "Depend on abstractions, not on concretions." - Robert C. Martin

High-level modules should not depend on low-level modules. Both should depend on abstractions. This enables testing, flexibility, and maintainability.

#### ✅ Good Example
```java
// Depend on interface, not implementation
interface PaymentProcessor {
    ProcessResult process(Payment payment);
}

class OrderService {
    private final PaymentProcessor processor;
    
    // Inject the dependency
    public OrderService(PaymentProcessor processor) {
        this.processor = processor;
    }
    
    public void completeOrder(Order order) {
        processor.process(order.getPayment());
    }
}

// Can swap implementations easily
PaymentProcessor stripeProcessor = new StripeProcessor();
PaymentProcessor paypalProcessor = new PayPalProcessor();
```

#### ❌ Anti-pattern
```java
class OrderService {
    // Hard-coded dependency
    private StripeProcessor processor = new StripeProcessor();
    
    public void completeOrder(Order order) {
        processor.process(order.getPayment()); // Tightly coupled
    }
}
```

### 2.2 Open/Closed Principle
**Original**: "Software entities should be open for extension, but closed for modification." - Bertrand Meyer

Add new functionality by adding new code, not by changing existing code that works.

#### ✅ Good Example
```python
# Base class defines contract
class DiscountStrategy:
    def calculate(self, order_total):
        raise NotImplementedError

# Extend without modifying
class PercentageDiscount(DiscountStrategy):
    def __init__(self, percentage):
        self.percentage = percentage
    
    def calculate(self, order_total):
        return order_total * (self.percentage / 100)

class FixedAmountDiscount(DiscountStrategy):
    def __init__(self, amount):
        self.amount = amount
    
    def calculate(self, order_total):
        return min(self.amount, order_total)

# New discount types can be added without changing existing code
```

#### ❌ Anti-pattern
```python
def calculate_discount(order_total, discount_type):
    # Must modify this function for every new discount type
    if discount_type == "percentage":
        return order_total * 0.1
    elif discount_type == "fixed":
        return 10
    elif discount_type == "bogo":  # Adding features requires modification
        return order_total * 0.5
```

## 3. Development Practices

### 3.1 Fail Fast and Explicitly
**Original**: "Errors should never pass silently." - Tim Peters, The Zen of Python

Detect and report errors as early as possible. Fail with clear, actionable error messages at the point of failure, not later when debugging becomes difficult.

#### ✅ Good Example
```javascript
function processPayment(amount, currency) {
  // Validate immediately
  if (!amount || amount <= 0) {
    throw new Error(`Invalid payment amount: ${amount}. Amount must be positive.`);
  }
  
  if (!SUPPORTED_CURRENCIES.includes(currency)) {
    throw new Error(
      `Unsupported currency: ${currency}. ` +
      `Supported currencies are: ${SUPPORTED_CURRENCIES.join(', ')}`
    );
  }
  
  // Process only after validation
  return paymentGateway.charge(amount, currency);
}
```

#### ❌ Anti-pattern
```javascript
function processPayment(amount, currency) {
  try {
    // Silent failures and unclear errors
    return paymentGateway.charge(amount || 0, currency || 'USD');
  } catch (e) {
    console.log('Payment failed'); // Swallowing error details
    return null; // Hiding the failure
  }
}
```

### 3.2 Test-Driven Development Mindset
**Original**: "Write tests first to drive design and ensure correctness." - Kent Beck

Even when not strictly following TDD, think about testability. Code that's hard to test is often poorly designed.

#### ✅ Good Example
```python
# Testable design with clear inputs/outputs
def calculate_shipping_cost(weight_kg, distance_km, express=False):
    """
    Calculate shipping cost based on weight and distance.
    
    Returns:
        float: Shipping cost in dollars
    Raises:
        ValueError: If weight or distance is negative
    """
    if weight_kg < 0 or distance_km < 0:
        raise ValueError("Weight and distance must be non-negative")
    
    base_cost = weight_kg * 0.5 + distance_km * 0.1
    return base_cost * 1.5 if express else base_cost

# Easy to test
def test_standard_shipping():
    assert calculate_shipping_cost(10, 100) == 15.0

def test_express_shipping():
    assert calculate_shipping_cost(10, 100, express=True) == 22.5
```

#### ❌ Anti-pattern
```python
# Hard to test due to external dependencies and side effects
def process_order():
    weight = database.get_order_weight()  # External dependency
    distance = external_api.calculate_distance()  # Another dependency
    cost = weight * 0.5 + distance * 0.1
    print(f"Shipping cost: {cost}")  # Side effect
    database.save_cost(cost)  # Side effect
    email_service.send_notification()  # Side effect
    return "Success"  # Vague return value
```

## 4. AI Collaboration Patterns

### 4.1 Context-First Development
When requesting code generation or modifications, provide clear context using the four-component pattern:

1. **Persona**: Define the role ("You are a senior backend engineer")
2. **Context**: Provide relevant background and constraints
3. **Task**: Specify exactly what needs to be done
4. **Format**: Define expected output structure

#### ✅ Good Example
```markdown
Persona: Senior full-stack developer experienced with React and Node.js
Context: Building an e-commerce checkout flow that must be PCI compliant
Task: Create a payment form component that tokenizes card data client-side
Format: React functional component with TypeScript, including error handling
```

### 4.2 Incremental Building Pattern
Build complex features incrementally. Start with core functionality, then layer in edge cases, error handling, and optimizations.

#### ✅ Good Progression
```
1. Create basic data model
2. Add validation rules
3. Implement happy path
4. Add error handling
5. Include edge cases
6. Optimize performance
7. Add monitoring/logging
```

## 5. Security and Performance

### 5.1 Security by Default
**Principle**: "Never trust user input. Validate and sanitize everything."

Security isn't optional or an afterthought. Every piece of user input is potentially malicious until proven otherwise.

#### ✅ Good Example
```javascript
// Parameterized queries prevent SQL injection
async function getUser(userId) {
  // Validate input type and format
  if (!userId || typeof userId !== 'string' || !UUID_REGEX.test(userId)) {
    throw new ValidationError('Invalid user ID format');
  }
  
  // Use parameterized query
  const query = 'SELECT * FROM users WHERE id = $1 AND deleted_at IS NULL';
  const result = await db.query(query, [userId]);
  
  // Sanitize output
  return sanitizeUserData(result.rows[0]);
}
```

#### ❌ Anti-pattern
```javascript
// Direct string concatenation enables injection
async function getUser(userId) {
  const query = `SELECT * FROM users WHERE id = '${userId}'`;
  return await db.query(query);
}
```

## Verification Checklist

Before committing code, verify:

- [ ] **Single Responsibility**: Each module/function has ONE clear purpose
- [ ] **No Duplication**: Business logic exists in exactly one place
- [ ] **Clear Intent**: Another developer can understand without comments
- [ ] **Dependency Injection**: Dependencies are injected, not hard-coded
- [ ] **Error Handling**: Errors fail fast with clear messages
- [ ] **Testable**: Code can be tested in isolation
- [ ] **Secure**: All inputs validated, outputs sanitized
- [ ] **Incremental**: Complex features built step-by-step

## Priority Order

When principles conflict, apply this precedence:
1. **Security** - Never compromise on security
2. **Correctness** - Working code over elegant code
3. **Maintainability** - Future developers over current convenience
4. **Performance** - Optimize only after measuring
5. **Features** - Core functionality before nice-to-haves

---

*Remember: These principles are guidelines, not dogma. Use judgment and context to apply them appropriately.*