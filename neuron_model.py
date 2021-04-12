# -*- coding: utf-8 -*-
"""
Single neuron circuit model. Circuit consists of a parallel interconnection of
an arbitrary number of either 'Current' or 'Conductance' elements

@author: Luka
"""
from numpy import tanh, exp
import numpy as np
from scipy.integrate import solve_ivp, BDF

def sigmoid(x, k = 1):
    return 1 / (1 + exp(-k * (x)))

class EulerSolver():
    def __init__(self, odesys, t0, y0, dt):
        self.odesys = odesys
        self.t = t0
        self.y = y0
        self.dt = dt
        
    def step(self):
        self.y += self.odesys(self.t,self.y)*self.dt
        self.t += self.dt
        
        # Return error message for compatibility with scipy solvers
        errorMessage = False
        return errorMessage

class System():
    """
    Parent class implementing basic simulation methods
    """
    def __init__(self):
        self.y0 = []
    
    def sys(self):
        pass
    
    def set_solver(self, solver, i_app, t0, sstep, dt = 1):
        def odesys(t, y):
            return self.sys(i_app(t), y)
        
        if (solver == "Euler"):
            self.solver = EulerSolver(odesys, t0, self.y0, dt)  
        elif (solver == "BDF"):
            self.solver = BDF(odesys, t0, self.y0, np.inf, max_step = sstep)
        else:
            raise ValueError("Undefined solver")
    
    def step(self):
        msg = self.solver.step()
        t = self.solver.t
        y = self.solver.y
        if msg:
            raise ValueError('Solver terminated with message: %s ' % msg)
            
        return t,y
    
    def simulate(self, trange, i_app, method = "Default", dt = 1):
        def odesys(t, y):
            return self.sys(i_app(t), y)
        
        if (method == "Default"):
            sol = solve_ivp(odesys, trange, self.y0)
        elif (method == "Euler"):
            print("Implement this")
        else:
            raise ValueError("Undefined solver")
            
        return sol
        

class SingleTimescaleElement():
    """
    Parent class for elements depending on a single filtered voltage Vx
    
    neuron: pointer to the neuron containing the element
    timescale: required for every element
    v0: initial condition
    v_index: index of Vx, assigned when interconnected in a circuit
    """
    
    vx0 = None # Default initial conditions for first-order filters
    
    def __init__(self, neuron, timescale, v0):
        self.neuron = neuron
        self.timescale = timescale
        self.v0 = v0
        self.v_index = None
        
        if (timescale == 0) and (v0 is not None):
            raise ValueError("Initial condition of an instantaneous element "
                             "cannot be set")
        
        self._add_timescale(neuron.timescales, neuron.y0)
    
    def _add_timescale(self, timescales, y0):
        """
        Add a first-order filter for Vx, or associate the element with an
        existing Vx
        """
        
        if (self.timescale in timescales) and (self.v0 is None):
            self.v_index = timescales.index(self.timescale)
        else:
            timescales.append(self.timescale)
            self.v_index = len(timescales) - 1
            if (self.v0):
                y0.append(self.v0)
            else:
                y0.append(self.vx0)
                
    def out(self, V):
        """
        Steady-state output depending on the input V
        """
        return V
    
    def outx(self, y):
        """
        Output depending on the appropriate Vx
        """
        return self.out(y[self.v_index])
    
    def IV(self, V, tau, Vrest = 0):
        """
        I-V curve of the element in timescale tau
        """
        if (self.timescale <= tau):
            return self.out(V)
        else:
            return self.out(Vrest)
        
class Neuron(System):
    """
    Parallel interconnection of current or conductance elements
    C dV/dT = - sum(I_x) + Iapp
    where I_x is the output current of each current/conductance element

    kwargs: circuit parameters (membrane capapcitance, initial condition)
    """

    # Membrane capacitor value + init conditions
    _stdPar = {'C': 1, 'v0': -1.9, 'vx0': -1.8}
    
    @property
    def stdPar(self):
        return type(self)._stdPar
    
    def __init__(self, **kwargs):
        self.__dict__.update(self.stdPar) # Default circuit parameters
        self.__dict__.update(kwargs) # Modify circuit parameters
        
        SingleTimescaleElement.vx0 = self.vx0 # Default initial conditions
        
        self.timescales = [0] # Timescales of membrane voltage + all filters
        self.y0 = [self.v0] # Initial conditions
                
        self.elements = [] # List containing all circuit elements
        
    # Functions for interconnecting individual elements
    def add_current(self, a, voff, timescale, v0 = None):
        I = self.CurrentElement(self, a, voff, timescale, v0)
        self.elements.append(I)
        return I
        
    def add_conductance(self, g_max, E_rev = 0):
        I = self.ConductanceElement(self, g_max, E_rev)
        self.elements.append(I)
        return I
                
    class CurrentElement(SingleTimescaleElement):
        """
        Current element of the form:
            Iout = a * tanh(Vx - voff).
            taux * dVx/dt = Vmem - Vx
        """                                
        
        def __init__(self, neuron, a, voff, timescale, v0):
            super().__init__(neuron, timescale, v0)
                        
            self.a = a
            self.voff = voff
            
        def out(self, V):
            return (self.a * tanh(V - self.voff))
        
        def update_a(self, a):
            self.a = a
            
        def update_voff(self, voff):
            self.voff = voff
            
    class ConductanceElement:
        """
        Single conductance element consisting of multiple gates:
            Iout = g_max * x1 * x2 * ... * xn * (V - E_rev)
            *args: [x1,x2,...,xn] = gates
        """
        def __init__(self, neuron, g_max, E_rev = 0):
            self.neuron = neuron
            self.g_max = g_max
            self.E_rev = E_rev
            self.gates = []
            
        class Gate(SingleTimescaleElement):
            """
            Single gating variable with sigmoidal activation/inactivation:
                x = S(k*(Vx - voff))
                taux * dVx/dt = Vmem - Vx
            """
            
            def __init__(self, neuron, k, voff, timescale, v0):
                super().__init__(neuron, timescale, v0)
                    
                self.k = k
                self.voff = voff
                   
            def out(self, V):
                return sigmoid(V - self.voff, self.k)
            
            def update_voff(self, voff):
                self.voff = voff
                
            def update_k(self, k):
                self.k = k
        
        # Add a gating variable to the conductance element
        def add_gate(self, k, voff, timescale, v0 = None):
            x = self.Gate(self.neuron, k, voff, timescale, v0)
            self.gates.append(x)
            return x
        
        def out(self, V):
            iout = self.g_max * (V - self.E_rev)
            for x in self.gates:
                iout *= x.out(V)
            return iout  
        
        def outx(self, y):
            iout = self.g_max * (y[0] - self.E_rev)
            for x in self.gates:
                iout *= x.outx(y)
            return iout
        
        def update_g_max(self, g_max):
            self.g_max = g_max
            
        def update_E_rev(self, E_rev):
            self.E_rev = E_rev
        
        def IV(self, V, tau, Vrest = 0):
            I = self.g_max * (V - self.E_rev)
            gates_fast = [g for g in self.gates if g.timescale <= tau]
            gates_slow = [g for g in self.gates if g.timescale > tau]
            
            for g in gates_fast:
                I *= g.out(V)
            
            for g in gates_slow:
                I *= g.out(Vrest)
            
            return I
    
    def IV(self, V, tau, Vrest = 0):
        I = 0
        for el in self.elements:
            I += el.IV(V, tau, Vrest)
        
        return I
    
    def IV_ss(self, V):
        I = 0
        for el in self.elements:
            I += el.out(V)
            
        return I
        
    def get_init_conditions(self):
        return np.array(self.y0)
    
    def i_sum(self, y):
        """
        Returns total internal current
        """
        s = 0
        for el in self.elements:
            s += el.outx(y)
        return s
    
    def sys(self, i_app, y):
        """
        Returns the state vector update
        y[0] = membrane voltage
        y[1],y[2],... = Element first-order filters, in order of definition
        """
        dy = []
        dvmem = (i_app - self.i_sum(y)) / self.C
        dy.append(dvmem)
        
        # First-order filters
        for index, tau in enumerate(self.timescales[1:]):
            dy.append((y[0] - y[index+1]) / tau)
        
        return np.array(dy)        