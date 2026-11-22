import tplot, matplotlib.pyplot as plt, numpy as np
x = np.linspace(0, 10, 300)
plt.plot(x, np.sin(x), label="sin"); plt.plot(x, np.exp(-x/4)*np.cos(3*x), label="damped")
plt.legend(); plt.title("tplot demo"); plt.show(size="70x20")
