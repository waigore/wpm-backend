# Clean Coding Principles

## Purpose

This document defines the clean coding principles that all code in the wpm-backend (Wealth Portfolio Manager Backend) project must adhere to. These principles are enforced through code review and should be referenced in all module specifications.

## Principles

### 1. Build Abstractions and Implement Delegation + Encapsulation

**Principle:** Always build abstractions and implement delegation and encapsulation whenever possible. High-level components should never need to know implementation details of lower-level components.

**Examples:**
- API routes should delegate to service layer functions rather than containing business logic. The `routes.py` module should handle HTTP request/response concerns, while `portfolio_service.py` contains the actual business logic.
- Services should abstract away external library details. The `portfolio_service` module transforms wpm library types to API models, so routes don't need to know about wpm library internals.
- Configuration should be accessed through dependency injection (FastAPI's `Depends`) rather than global state. Use `get_settings()` as a dependency rather than importing a global settings instance.
- Components should encapsulate their internal state and expose only necessary interfaces. For example, authentication logic is encapsulated in the `auth` module and accessed through clear function interfaces.
- Use dependency injection patterns (FastAPI `Depends`) to decouple components and make dependencies explicit.

**Enforcement:**
- When reviewing code, verify that route handlers delegate to service functions rather than containing business logic.
- Check that service layer functions abstract away external library (wpm) implementation details.
- Ensure that internal implementation details (like JWT token structure) are not exposed beyond module boundaries.
- Verify that dependencies are injected via FastAPI `Depends` rather than accessed as globals.

### 2. Avoid Nested Conditionals - Use Conditional Guards

**Principle:** Nested conditionals are a code smell and should be avoided. Prefer conditional guards (early returns/continues) to flatten control logic. If control logic is still too complicated (e.g., 3 or more nested layers), abstract it away into a class or function.

**Rule:** Never have more than 2 levels of nested if statements.

**Examples:**

**Bad:**
```python
if condition_a:
    if condition_b:
        if condition_c:
            # do work
        else:
            pass
    else:
        pass
else:
    pass
```

**Better (with guards):**
```python
if not condition_a:
    return  # or continue, or handle early case

if not condition_b:
    return

if not condition_c:
    return

# do work
```

**When to Abstract:**
- If after applying guard clauses, you still have 3+ levels of nesting, extract the logic into a separate function or class.
- Complex conditional logic that represents a distinct decision point should be encapsulated in a method with a descriptive name.

**Enforcement:**
- Code reviews must flag any code with more than 2 levels of nested conditionals.
- Prefer guard clauses (`if not condition: return/continue`) over nested if-else blocks.
- Extract complex conditional logic into well-named helper methods or classes.

### 3. Avoid Inline Imports

**Principle:** Avoid inline imports (imports inside functions or methods) as they build hidden dependencies and contribute to undesired coupling. All imports should be at the module level.

**Rationale:**
- Inline imports make dependencies less visible and harder to track.
- They can create circular import issues.
- They make it difficult to understand module dependencies at a glance.
- They can lead to performance issues if imports happen in hot paths.

**Examples:**

**Bad:**
```python
@router.get("/portfolio/all")
def get_all_positions_endpoint(request: Request):
    from wpm_backend.services.portfolio_service import get_all_positions
    from wpm_backend.models.portfolio import PortfolioResponse
    composite = request.app.state.composite_portfolio
    positions = get_all_positions(composite, price_service)
    return PortfolioResponse(positions=positions)
```

**Better:**
```python
from wpm_backend.services.portfolio_service import get_all_positions
from wpm_backend.models.portfolio import PortfolioResponse

@router.get("/portfolio/all")
def get_all_positions_endpoint(request: Request):
    composite = request.app.state.composite_portfolio
    positions = get_all_positions(composite, price_service)
    return PortfolioResponse(positions=positions)
```

**Exceptions:**
- Only acceptable when importing inside a function is necessary to break a circular import, and this should be documented with a comment explaining why.

**Enforcement:**
- All imports must be at the top of the file (after module docstring and before any other code).
- Code reviews must flag any inline imports and require justification if they cannot be moved to module level.

### 4. Avoid hasattr Unless Absolutely Necessary

**Principle:** Avoid using `hasattr()` unless absolutely necessary. `hasattr` degrades code quality and makes the program more brittle during execution.

**Rationale:**
- `hasattr` relies on dynamic attribute access, which bypasses static type checking and makes code harder to reason about.
- It creates implicit contracts that are not enforced by the type system or class definitions.
- Code using `hasattr` is more prone to runtime errors that could be caught earlier with proper type checking or explicit interfaces.
- It encourages a "duck typing gone wrong" approach where objects are expected to have certain attributes without clear guarantees.
- Makes refactoring more dangerous as attribute existence checks can silently fail or pass incorrectly.

**Examples:**

**Bad:**
```python
def get_portfolio_data(request: Request):
    if hasattr(request.app.state, 'composite_portfolio'):
        portfolio = request.app.state.composite_portfolio
        if hasattr(portfolio, 'get_positions'):
            return portfolio.get_positions()
    return None
```

**Better (using explicit attribute access with proper error handling):**
```python
def get_portfolio_data(request: Request) -> CompositePortfolio:
    portfolio = getattr(request.app.state, 'composite_portfolio', None)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Portfolio data not available"
        )
    return portfolio
```

**Better (using dependency injection and type hints):**
```python
from fastapi import Depends, Request
from wpm.portfolio import CompositePortfolio

def get_composite_portfolio(request: Request) -> CompositePortfolio:
    """Dependency function to get composite portfolio from app state."""
    portfolio = getattr(request.app.state, 'composite_portfolio', None)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Portfolio data not available"
        )
    return portfolio

@router.get("/portfolio/all")
def get_all_positions_endpoint(
    portfolio: CompositePortfolio = Depends(get_composite_portfolio)
):
    # Use portfolio directly with type safety
    return get_all_positions(portfolio, price_service)
```

**When hasattr is Acceptable:**
- Only when dealing with truly dynamic objects where attribute existence cannot be determined statically (e.g., parsing external data structures, working with third-party libraries that don't provide type hints).
- When the alternative would require significant architectural changes that are not feasible in the short term (should be documented and marked for refactoring).

**Enforcement:**
- Code reviews must flag all uses of `hasattr` and require justification.
- Prefer abstract base classes, protocols, or explicit type checking to define expected interfaces.
- Use optional methods with default implementations in base classes rather than checking for attribute existence.
- Document any legitimate uses of `hasattr` with comments explaining why it's necessary.

## FastAPI-Specific Patterns

This section provides guidance on applying these principles within the FastAPI framework used by this project.

### Dependency Injection

**Principle:** Use FastAPI's `Depends()` for dependency injection rather than global state or direct instantiation.

**Examples:**

**Bad:**
```python
from wpm_backend.config import Settings

_settings = Settings()

@router.get("/portfolio/all")
def get_all_positions_endpoint(request: Request):
    # Directly accessing global settings
    if _settings.username == "admin":
        # ...
```

**Better:**
```python
from wpm_backend.config import Settings, get_settings

@router.get("/portfolio/all")
def get_all_positions_endpoint(
    request: Request,
    settings: Settings = Depends(get_settings)
):
    # Settings injected via dependency
    if settings.username == "admin":
        # ...
```

### Route Handler Responsibilities

**Principle:** Route handlers should be thin - they handle HTTP concerns (request/response, status codes) and delegate business logic to service layer functions.

**Examples:**

**Bad:**
```python
@router.get("/portfolio/all")
def get_all_positions_endpoint(request: Request):
    # Business logic in route handler
    portfolio = request.app.state.composite_portfolio
    positions_dict = portfolio.get_positions()
    price_map = fetch_price_map(portfolio, price_service)
    # ... complex transformation logic ...
    return PortfolioResponse(positions=positions)
```

**Better:**
```python
@router.get("/portfolio/all", response_model=PortfolioResponse)
def get_all_positions_endpoint(
    request: Request,
    username: str = Depends(get_current_user)
) -> PortfolioResponse:
    # Delegate to service layer
    portfolio = request.app.state.composite_portfolio
    price_service = request.app.state.price_service
    positions = get_all_positions(portfolio, price_service)
    return PortfolioResponse(positions=positions)
```

### Error Handling

**Principle:** Use guard clauses and early returns in route handlers, raising HTTPException for error cases.

**Examples:**

**Bad:**
```python
@router.get("/portfolio/all")
def get_all_positions_endpoint(request: Request):
    if hasattr(request.app.state, 'composite_portfolio'):
        portfolio = request.app.state.composite_portfolio
        if portfolio is not None:
            if hasattr(request.app.state, 'price_service'):
                price_service = request.app.state.price_service
                if price_service is not None:
                    return get_all_positions(portfolio, price_service)
                else:
                    return {"error": "Price service not available"}
            else:
                return {"error": "Price service not available"}
        else:
            return {"error": "Portfolio not available"}
    else:
        return {"error": "Portfolio not available"}
```

**Better:**
```python
from fastapi import HTTPException, Request, status
from wpm_backend.models.portfolio import PortfolioResponse
from wpm_backend.services.portfolio_service import get_all_positions

@router.get("/portfolio/all")
def get_all_positions_endpoint(request: Request):
    portfolio = getattr(request.app.state, 'composite_portfolio', None)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Portfolio data not available"
        )
    
    price_service = getattr(request.app.state, 'price_service', None)
    if price_service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Price service not available"
        )
    
    positions = get_all_positions(portfolio, price_service)
    return PortfolioResponse(positions=positions)
```

### Type Safety with Pydantic Models

**Principle:** Use Pydantic models for request/response validation. Define models in the `models` package, not inline in route handlers.

**Examples:**

**Bad:**
```python
@router.post("/login")
def login(request_data: dict):
    username = request_data.get("username")
    password = request_data.get("password")
    # ...
```

**Better:**
```python
from wpm_backend.models.auth import LoginRequest, LoginResponse

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    # Pydantic handles validation automatically
    # ...
```

## Integration with Specifications

All module specifications should reference this document and explicitly state how the module adheres to these principles:

- **Abstraction/Delegation:** Describe the interfaces and abstractions the module provides (e.g., service layer abstractions, dependency injection patterns).
- **Control Flow:** Note any complex conditional logic and how it's been flattened or abstracted (e.g., guard clauses in route handlers).
- **Dependencies:** List all module-level imports and explain the module's dependencies. For route handlers, describe dependencies injected via FastAPI `Depends()`.
- **Type Safety:** Document any use of `hasattr` and justify why it's necessary, or describe the explicit interfaces/protocols used instead (e.g., Pydantic models for validation, type hints for function parameters).
- **FastAPI Patterns:** For API modules, describe how route handlers delegate to service layer and use dependency injection.

## Code Review Checklist

When reviewing code, verify:

- [ ] No more than 2 levels of nested conditionals
- [ ] Guard clauses are used to flatten control flow
- [ ] Complex logic is abstracted into functions/classes
- [ ] All imports are at module level (no inline imports)
- [ ] High-level components delegate to abstractions rather than implementing details
- [ ] Dependencies are explicit and visible
- [ ] `hasattr` is avoided unless absolutely necessary (with documented justification)
- [ ] Interfaces are defined using abstract base classes, protocols, or explicit type checking
- [ ] FastAPI dependencies use `Depends()` for injection rather than global state
- [ ] Route handlers are thin and delegate business logic to service layer
- [ ] Pydantic models are used for request/response validation
- [ ] HTTPException is raised for error cases rather than returning error dicts

## References

- See `SPEC/spec.md` for module-level requirements and architecture details
- These principles apply to all code in the wpm-backend (Wealth Portfolio Manager Backend) project

