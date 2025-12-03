import dis

def outer():
    x = 1
    def inner():
        return x + 1
    return inner

closure_func = outer()

print("Closure:")
print(closure_func.__code__.co_freevars)
print(closure_func.__code__.co_names)

