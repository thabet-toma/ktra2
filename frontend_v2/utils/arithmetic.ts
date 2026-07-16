const MAX_EXPRESSION_LENGTH = 256;

/**
 * Evaluates the calculator's deliberately small arithmetic grammar without
 * executing JavaScript. Supported input: decimal numbers, +, -, *, / and
 * whitespace. Unary + and - are supported; parentheses and identifiers are not.
 */
export function evaluateArithmeticExpression(expression: string): number {
  if (expression.length > MAX_EXPRESSION_LENGTH) {
    throw new Error("Expression is too long");
  }

  let position = 0;

  const skipWhitespace = () => {
    while (/\s/.test(expression[position] ?? "")) position += 1;
  };

  const parseNumber = (): number => {
    skipWhitespace();
    const start = position;
    let dotSeen = false;
    let digitSeen = false;

    while (position < expression.length) {
      const char = expression[position];
      if (char >= "0" && char <= "9") {
        digitSeen = true;
        position += 1;
      } else if (char === "." && !dotSeen) {
        dotSeen = true;
        position += 1;
      } else {
        break;
      }
    }

    if (!digitSeen) throw new Error("Expected a number");
    const value = Number(expression.slice(start, position));
    if (!Number.isFinite(value)) throw new Error("Invalid number");
    return value;
  };

  const parseUnary = (): number => {
    skipWhitespace();
    const operator = expression[position];
    if (operator === "+" || operator === "-") {
      position += 1;
      const value = parseUnary();
      return operator === "-" ? -value : value;
    }
    return parseNumber();
  };

  const parseTerm = (): number => {
    let value = parseUnary();
    while (true) {
      skipWhitespace();
      const operator = expression[position];
      if (operator !== "*" && operator !== "/") break;
      position += 1;
      const right = parseUnary();
      value = operator === "*" ? value * right : value / right;
      if (!Number.isFinite(value)) throw new Error("Invalid arithmetic result");
    }
    return value;
  };

  const parseExpression = (): number => {
    let value = parseTerm();
    while (true) {
      skipWhitespace();
      const operator = expression[position];
      if (operator !== "+" && operator !== "-") break;
      position += 1;
      const right = parseTerm();
      value = operator === "+" ? value + right : value - right;
    }
    return value;
  };

  skipWhitespace();
  if (position === expression.length) throw new Error("Expression is empty");
  const result = parseExpression();
  skipWhitespace();
  if (position !== expression.length || !Number.isFinite(result)) {
    throw new Error("Invalid expression");
  }
  return result;
}
