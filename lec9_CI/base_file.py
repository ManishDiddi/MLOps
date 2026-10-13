a = 5
b = 10

def add(x, y):
	return x + y

def subtract(x, y):
	return x - y

def multiply(x, y):
	return x * y

def divide(x, y):
	if y == 0:
		return "Cannot divide by zero"
	return x / y

print("This is a base file for session 6 on CI/CD, outside the main block.")


if __name__ == "__main__":

	print("This is a base file for session 6 on CI/CD.")
	print("Adding two numbers in base file:", add(a, b))
	print("Subtracting two numbers in base file:", subtract(a, b))
	print("Multiplying two numbers in base file:", multiply(a, b))
	print("Dividing two numbers in base file:", divide(a, b))
