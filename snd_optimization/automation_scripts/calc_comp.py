import matplotlib.pyplot as plt
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

#filename = '/cds/home/opr/xcsopr/experiments/xcs101611626/delay_scans/delay_scan_1784176936.npz'
filename = '/cds/home/opr/xcsopr/experiments/xcs101611626/delay_scans/delay_scan_1784179828.npz'
data = np.load(filename)
#file2 = '/cds/home/opr/xcsopr/experiments/xcs101611626/delay_scans/delay_scan_1784072471.npz'

#data =np.load(file2)

#x_matrix = [[0.35545, 0.02628],[-0.3491,-0.18678]]
#y_matrix = [[-2.073, -0.166],[2.6679,0.8262]]

# response matrices in degrees units
x_matrix = [[2.036e-5, 1.5058e-6],[-2e-5,-1.07e-5]]
y_matrix = [[-1.188e-4, -9.513e-6],[1.5286e-4,4.734e-5]]

IP_x = data['IP_x']
IP_y = data['IP_y']
do_x = data['do_x']
do_y = data['do_y']
delay = data['delay'][:301]

t1_th = np.zeros_like(delay)
t4_th = np.zeros_like(delay)
t1_chi = np.zeros_like(delay)
t4_chi = np.zeros_like(delay)

file2 = '/cds/home/opr/xcsopr/experiments/xcs101611626/delay_scans/delay_scan_1784072471.npz'

#data2 =np.load(file2)
#IPx2 = data2['IP_x']
#dox2 = data2['do_x']

window_size = 3
windows = sliding_window_view(do_x,window_shape=window_size)
rolling_mean = windows.mean(axis=1)
#
plt.figure()
plt.plot(do_x-do_x[50])
plt.title('do_x')
#plt.plot(dox2-dox2[50])
plt.figure()
plt.plot(IP_x-IP_x[50])
plt.title('IP_x')
#plt.plot(IPx2-IPx2[50])
##plt.plot(IP_x-IP_x[50])
plt.figure()
plt.plot(do_y-do_y[50])
plt.plot(IP_y-IP_y[50])
plt.title('y')
#
for i in range(301):
    comp = x_matrix@np.array([do_x[i]-do_x[50],IP_x[i]-IP_x[50]])
    t1_th[i] = comp[0]
    t4_th[i] = comp[1]
    comp = y_matrix@np.array([do_y[i]-do_y[50],IP_y[i]-IP_y[50]])
    t1_chi[i] = comp[0]
    t4_chi[i] = comp[1]


plt.figure()
plt.plot(delay[:301],t1_th)
plt.plot(delay[:301],t4_th)
plt.title('theta compensation')

plt.figure()
plt.plot(delay[:301],t1_chi)
plt.plot(delay[:301],t4_chi)
plt.title('chi compensation')

plt.figure()
plt.plot(delay,t1_th+t4_th)
plt.plot(delay,t1_chi+t4_chi)

np.savez('two_crystal_comp.npz',delay=delay,t1_th=t1_th,t4_th=t4_th,t1_chi=t1_chi,t4_chi=t4_chi)

plt.show()
