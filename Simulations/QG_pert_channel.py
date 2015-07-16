#!/usr/bin/env python
#  QG_pert_channel.m
#
# Solve the 1-Layer Quasi-Geostrophic (QG) Model
#
# Geometry: periodic in x and a channel in y
#
# Fields: 
#   q : Potential Vorticity
#   u : zonal velocity
#   v : meridional velocity
# psi : streamfunction
#
# Parameters:
#  U  : background velocity
#  F  : Froude number
#  Q_y: F*U + beta
#  
# Evolution Eqns:	
#   q_t = - (u + U) q_x - (q_y + Q_y) v
#
# Potential Vorticity:
#   q = psi_xx + psi_yy - F psi 
#   q_hat = - (K2 + F) psi_hat
#
# Geostrophy:
#   u = -psi_y
#   v =  psi_x
#
#   u_hat = -il*psi_hat =  il/(K2 + F)*q_hat
#   v_hat =  ik*psi_hat = -ik/(K2 + F)*b_hat
#
# Numerical Method:
# 1) FFT to compute the derivatives in spectral space
# 2) Adams-Bashforth for Advection
#
# Requires scripts:
#        flux_qg.py  - compute flux for the qg model

# Import libraries
from __future__ import division
import numpy as np
from numpy import linalg as LA
import scipy as np
import matplotlib.pyplot as plt
from scipy.fftpack import fft, ifft, fftn, ifftn
import sys

#try:
#    import pyfftw
#    from numpy import zeros as nzeros
#
#    # Keep fft objects in cache for efficiency
#    nthreads = 1
#    pyfftw.interfaces.cache.enable()
#    pyfftw.interfaces.cache.set_keepalive_time(1e8)
#    def empty(N, dtype="float", bytes=16):
#        return pyfftw.n_byte_align_empty(N, bytes, dtype=dtype)
#
#    def zeros(N, dtype="float", bytes=16):
#        return pyfftw.n_byte_align(nzeros(N, dtype=dtype), bytes)
#    
#    # Monkey patches for fft
#    ifft = pyfftw.interfaces.numpy_fft.ifft
#    fft = pyfftw.interfaces.numpy_fft.fft
#
#except:    
#    from scipy.fftpack import fft, ifft
#    print Warning("Install pyfftw, it is much faster than numpy fft")

def flux_qg(q, parms):

    # - (u + U) q_x - (q_y + Q_y) v
    qe = np.vstack((q,-np.flipud(q)))
    qe_hat = fftn(qe)

    # Compute gradient of PV
    q_x = (ifftn( parms.ikx*qe_hat)).real
    q_y = (ifftn( parms.iky*qe_hat)).real

    # Compute streamfunction
    psie_hat = parms.K2Fi*qe_hat
    psi = (ifftn(psie_hat)).real
        
    # Compute physical velocities
    u = (ifftn(-parms.iky*psie_hat)).real
    v = (ifftn( parms.ikx*psie_hat)).real

    # Restrict to physical domain
    q_x = q_x[0:parms.Ny,:]
    q_y = q_y[0:parms.Ny,:]
    u   = u[0:parms.Ny,:]
    v   = v[0:parms.Ny,:]
    psi = psi[0:parms.Ny,:]

    # Compute flux
    flux = - (u + parms.U)*q_x - (q_y + parms.Q_y)*v
    
    # FJP: energy should include potential energy
    energy = 0.5*np.mean(u**2 + v**2) + np.mean(parms.F*psi**2)
    enstr  = np.mean(q**2)
    mass   = np.mean(psi)
    
    return flux, energy, enstr, mass


#######################################################
#        Parameters Class                             #
#######################################################

class Parms(object):
    """A class to solve the one-layer QG model in a channel."""
    
    def __init__(
        self,
        # Grid size parameters
        Nx=128,                     # x-grid resolution
        Ny=128,                     # y-grid resolution
        Lx=1000e3,                  # zonal domain size 
        Ly=1000e3,                  # meridional domain size 
                 
        # Physical parameters
        g0  = 9.81,                 # (reduced) gravity
        H0  = 1000,                 # mean depth
        f0  = 1e-4,                 # Coriolis parameter
        beta= 1e-11,                # gradient of coriolis parameter

        # Timestepping parameters
        t0  = 0.0,                   # Initial time
        dt  = 3600.,                # Timestep
        tf  = 20.*3600.*24.,         # Final time
        npt = 12,                    # Frequency of plotting
    ):

        # Save parameters
        self.Nx = Nx
        self.Ny = Ny
        self.Lx = Lx
        self.Ly = Ly
        self.g0 = g0
        self.H0 = H0
        self.beta = beta
        self.t0 = t0
        self.dt = dt
        self.tf = tf
        self.npt = npt
        self.tplot = dt*npt

        # Physical parameters
        dx  = Lx/Nx
        dy  = Ly/Ny
        F   = 0*(f0/(g0*H0))**2
        U   = 0
        
        self.dx = dx
        self.dy = dy
        self.F   = F
        self.U   = U
        self.Q_y = F*U + beta
    
        # Define Grid
        x = np.linspace(-Lx/2+dx/2,Lx/2-dx/2,Nx)
        y = np.linspace(-Ly/2+dy/2,Ly/2-dy/2,Ny)
        xx,yy = np.meshgrid(x,y)
        self.xx = xx
        self.yy = yy
        
        #  Define wavenumber (frequency)
        kx = 2*np.pi/Lx*np.hstack([range(0,int(Nx/2)+1), range(-int(Nx/2)+1,0)])
        ky = np.pi/Ly*np.hstack([range(0,Ny+1), range(-Ny+1,0)])
        kxx, kyy = np.meshgrid(kx,ky)
        K2Fi = -1./(kxx**2 + kyy**2 + F)
        if F == 0:
            K2Fi[0,0] = 0.
        else:
            K2Fi[0,0] = -1./F

        # Save parameters    
        self.ikx = 1j*kxx
        self.iky = 1j*kyy
        self.K2Fi = K2Fi
        self.xx = xx
        self.yy = yy

        #omega = -beta*(2*np.pi/Lx)/((np.pi/Ly)**2 + (2*np.pi/Lx)**2)

        # Filter Parameters
        kmax = max(kx);
        ks = 0.4*kmax;
        km = 0.5*kmax;
        alpha = 0.69*ks**(-1.88/np.log(km/ks));
        beta  = 1.88/np.log(km/ks);
        self.sfilt = np.exp(-alpha*(kxx**2 + kyy**2)**(beta/2.0));

#######################################################
#        Solve 1-Layer QG model in a channel          #
#######################################################

def solve_qg(parms, q0):

    # Set parameters
    dt = parms.dt
    Nx = parms.Nx
    Ny = parms.Ny
    
    # initialize fields
    Nt = int(parms.tf/parms.dt)
    energy = np.zeros(Nt)
    enstr  = np.zeros(Nt)
    mass   = np.zeros(Nt)
    
    # Euler step
    t,ii = 0., 0 
    NLnm, energy[0], enstr[0], mass[0] = flux_qg(q0, parms)
    q  = q0 + dt*NLnm;

    # AB2 step
    t,ii = parms.dt, 1 
    NLn, energy[1], enstr[1], mass[1] = flux_qg(q, parms)
    q   = q + 0.5*dt*(3*NLn - NLnm)

    cnt = 2
    for ii in range(3,Nt+1):

        # AB3 step
        t = (ii-1)*parms.dt
        NL, energy[ii-1], enstr[ii-1], mass[ii-1] = flux_qg(q, parms)
        q  = q + dt/12*(23*NL - 16*NLn + 5*NLnm).real
        
        # Exponential Filter
        qe = np.vstack((q,-np.flipud(q)))
        qe = (ifftn(parms.sfilt*fftn(qe))).real
        q  = qe[0:Ny,:]

        # Reset fluxes
        NLnm = NLn
        NLn  = NL

        if (ii-0)%parms.npt==0:

            # make title
            name = "PV at t = %5.2f" % (t/(3600.0*24.0))
            
            # Plot PV (or streamfunction)
            plt.clf()
            plt.pcolormesh(xx/1e3,yy/1e3,q)
            plt.colorbar()
            plt.title(name)
            plt.axes([-Lx/2, Lx/2, -Ly/2, Ly/2])
            plt.draw()

            cnt += 1

    return q, energy, enstr, mass

#######################################################
#         Main Program                                #
#######################################################

# Numerical parameters

# Set parameters
parms = Parms()

# Initial Conditions
Lx = parms.Lx
Ly = parms.Ly
xx = parms.xx
yy = parms.yy
q0  = 1e-8*np.sin(1.0*np.pi*(yy+Ly/2)/Ly)*np.cos(2*np.pi*(xx+Lx/2)/Lx)

# Prepare animation
plt.ion()
plt.clf()
plt.pcolormesh(xx/1e3,yy/1e3,q0)
plt.colorbar()
plt.title( "PV at t = 0.00")
plt.axes([-Lx/2, Lx/2, -Ly/2, Ly/2])
#plt.draw()
plt.show()

# Find Solution
q, energy, enstr, mass = solve_qg(parms,q0)

plt.ioff()
plt.show()

# Diagnostics
print "Error in energy is ", np.amax(energy-energy[1])/energy[1]
print "Error in enstrophy is ", np.amax(enstr-enstr[1])/enstr[1]
print "Error in mass is ", np.amax(mass-mass[1])/mass[1]

plt.figure()
fig, axarr = plt.subplots(3, sharex=True)
ax1 = plt.subplot(3,1,1)
ax2 = plt.subplot(3,1,2)
ax3 = plt.subplot(3,1,3)
ax1.plot((energy-energy[0]),'-ob',linewidth=2, label='Energy')
ax1.set_title('Energy')
ax2.plot((enstr-enstr[0]),'-or', linewidth=2, label='Enstrophy')
ax2.set_title('Enstrophy')
ax3.plot((mass-mass[0]),'-or', linewidth=2, label='Enstrophy')
ax3.set_title('Mass')
plt.show()
