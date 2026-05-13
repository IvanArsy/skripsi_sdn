import numpy as np

def pilih_rute_terbaik(matriks_data):
    """
    matriks_data: List dari list berisi [Throughput, Latency, Loss] untuk tiap jalur
    Return: Index (angka) dari jalur terbaik
    """
    if len(matriks_data) == 1:
        return 0
        
    X = np.array(matriks_data, dtype=float)
    
    X[X == 0] = 0.0001 
    
    W = np.array([0.4, 0.2, 0.4], dtype=float)
    
    sifat_kriteria = [True, False, False]
    
    pembagi = np.sqrt(np.sum(X**2, axis=0))
    R = X / pembagi
    
    V = R * W
    
    A_plus = np.zeros(X.shape[1])
    A_minus = np.zeros(X.shape[1])
    
    for j in range(X.shape[1]):
        if sifat_kriteria[j]: 
            A_plus[j] = np.max(V[:, j])
            A_minus[j] = np.min(V[:, j])
        else:                 
            A_plus[j] = np.min(V[:, j])
            A_minus[j] = np.max(V[:, j])
            
    D_plus = np.sqrt(np.sum((V - A_plus)**2, axis=1))
    D_minus = np.sqrt(np.sum((V - A_minus)**2, axis=1))
    
    Skor = D_minus / (D_plus + D_minus + 1e-10) 
    
    jalur_terbaik_idx = np.argmax(Skor)
    return jalur_terbaik_idx