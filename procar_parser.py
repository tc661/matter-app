# procar_parser.py

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import CheckButtons, Slider, Button
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.backends.backend_pdf import PdfPages
import itertools

#=========== INTERACTIVE CLASSES ==============

class DraggableHLine:
    """Draggable horizontal line for matplotlib"""
    def __init__(self, ax, y, color='cyan', linestyle="--", label=None):
        self.ax = ax
        self.line = ax.axhline(y, color=color, linestyle=linestyle, linewidth=2.0, picker=5)
        self.line.set_zorder(100)

        if label:
            self.text = ax.text(0.99, y, va='center', ha='right',
                                transform=ax.get_yaxis_transform(), fontsize=8)
            self.text.set_zorder(101)
        else:
            self.text = None

        self.press = None
        self.on_change_callback = None
        self.cid_press = self.line.figure.canvas.mpl_connect('button_press_event', self.on_press)
        self.cid_release = self.line.figure.canvas.mpl_connect('button_release_event', self.on_release)
        self.cid_motion = self.line.figure.canvas.mpl_connect('motion_notify_event', self.on_motion)

    def on_press(self, event):
        if event.inaxes != self.ax: return
        contains, _ = self.line.contains(event)
        if contains:
            self.press = event.ydata
    
    def on_motion(self, event):
        if self.press is None or event.inaxes != self.ax: return
        y = event.ydata
        self.line.set_ydata([y, y])
        if self.text is not None:
            self.text.set_position((0.99, y))
        """
        # call the registered callback continuously so UI updates while dragging
        if self.on_change_callback is not None:
            try:
                self.on_change_callback()
            except Exception:
                pass
        """
        self.line.figure.canvas.draw_idle()

    def on_release(self, event):
        self.press = None
        # ensure a final update
        if self.on_change_callback is not None:
            try:
                self.on_change_callback()
            except Exception:
                pass

    def get_y(self):
        return self.line.get_ydata()[0]

#=========== POTENTIAL PROCAR CLASS ===========

class Parser:

    def __init__(self, procar_path=None, fermi_path=None):
        self.procar = (self.PROCAR(procar_path) if procar_path else None)
        self.fermi = (self.FERMI(fermi_path) if fermi_path else None)


    def PROCAR(self, procar_path):
        """CREATES PROCAR DICT:

        procar = {"header", "kpoints"}
            header = {"title", "kpoints", "bands", "ions", "orbitals"}
                orbitals = [orb(str)]
            kpoints = [kp(dict)]
                kp = {"index", "coords", "weight", "bands"}
                    coords = [coord(float)]
                    bands = [band(dict)]
                        band = {"index" "energy" "occupancy" "ions" "total"}
                            ions = [ion(dict)]
                                ion = {"orb1" ... "orbN" "total"}
                            total = {"orb1" ... "orbN" "total"}

        """
        try:
            with open(procar_path, 'r') as f:
                print("Reading PROCAR lines")
                lines = f.readlines()
                print("Splitting PROCAR lines")
                for i, line in enumerate(lines):
                    lines[i] = line.split()
                
                # PROCAR lm decomposed
                title = ' '.join(lines[0])
                #   # of k-points: [nk]   # of bands: [nb]  # of ions: [nions]
                nk = int(lines[1][3])   
                nb = int(lines[1][7])
                nion = int(lines[1][11])
                #ion      s     py     pz     px    dxy    dyz    dz2    dxz  x2-y2    tot
                orbitals = lines[7][1:-1]

                procar = {} # procar{header(dict), kpoints(arr of dict)}
                procar["header"] = {
                    "title": title,
                    "kpoints": nk,
                    "bands": nb,
                    "ions": nion,
                    "orbitals": orbitals
                        }

                print(f"PROCAR header: {procar['header'].items()}")

                n =2
                #=========================================
                procar["kpoints"] = []
                for k_idx in range(1, nk+1):
                    print(f"Parsing K-Point {k_idx}")
                    kpoint = {} # kpoint{index(int), coordinates(arr of floats), weight(float), bands(arr of dict)}
                    n += 1
                    # k-point   [k_idx] : [coordx] [coordy] [coordz]   weight = [weight]
                    # KPOINTS
                    kpoint["index"] = k_idx
                    kpoint["coordinates"] = []
                    for coordinate in lines[n][3:6]:
                        kpoint["coordinates"].append(float(coordinate))
                    kpoint["weight"] = float(lines[n][8])
                    kpoint["bands"] = []

                    for b_idx in range(1, nb+1):
                        # print(f"Parsing band {b_idx}")
                        band = {} # band{index(int), energy(float), occupancy(float), orbitals(dict)}
                        n += 2
                        # band  [b_idx] # energy [energy] # occ. [occupancy]
                        # BANDS
                        band["index"] = b_idx
                        band["energy"] = float(lines[n][4])
                        band["occupancy"] = float(lines[n][7])
                        band["ions"] = []
                        n += 2
                        # ion   s   py      pz      px      dxy     dyz     dz2    dxz  x2-y2    tot
                        for i_idx in range(1, nion+1):
                            ion = {} # ion{index(int, s(float)... tot(float)}
                            ion["index"] = i_idx
                            n += 1
                            # [ion]   [s]   [py]      [pz]    [px]     [dxy]   [dyz]   [dz2]  [dxz]  [x2-y2]  [tot]
                            for i, orbital in enumerate(procar["header"]["orbitals"]):
                                ion[orbital] = float(lines[n][i+1])
                                ion["total"] = float(lines[n][-1])
                            band["ions"].append(ion)
                        
                        n += 1
                        band["total"] = {}
                        for i, orbital in enumerate(procar["header"]["orbitals"]):
                                band["total"][orbital] = float(lines[n][i+1])
                                band["total"]["total"] = float(lines[n][-1])
                        
                        kpoint["bands"].append(band)
                    

                    procar["kpoints"].append(kpoint)
                    n += 2
            return procar
        except Exception as e:
            print(f"Error: {e}")
            return None
    

    def FERMI(self, fermi_path):
        try:
            with open(fermi_path, 'r') as f:
                lines = f.readlines()
                return float(lines[0])
        except:
            print("FERMI ENERGY NOT FOUND")
            return 0        

#========================== Band Data Class ============================

class BandData:

    def __init__(self, procar_dict, fermi=0.0):
        self.procar = procar_dict
        self.fermi = float(fermi)
        if self.procar is not None:
            self.energies = self._compute_energies() # shape (nb, nk)
            self.weights, self.band_weights = self._compute_weights() # shapes (nb, nion, norb) and (nb,)

            self._per_kpoint_weights = None
            self._orb_index = {orb: i for i, orb in enumerate(self.procar["header"]["orbitals"])}


    def _compute_energies(self):
        """Returns array (nb, nk) of energies for each band
        energies = [band(arr) for all bands]
            band = [energy(float) for all kpoints]
        """
        nk = self.procar["header"]["kpoints"]
        nb = self.procar["header"]["bands"]
        energies = [[0.0 for _ in range(nk)] for _ in range(nb)]
        for k_idx, kp in enumerate(self.procar["kpoints"]):
            for band in kp["bands"]:
                b_idx = band["index"] - 1
                energies[b_idx][k_idx] = band["energy"]
        return np.array(energies)
    

    def _compute_weights(self):
        """RETURNS ARRAY (nb, nion, norb) OF WEIGHTS FOR EACH BAND
        weights = [band(arr) for all bands]
            band = [ion(dict) for all ions]
                ion = {"orb1" ... "orbN"}
        total_weights = [weight for all bands]

        Returns ARRAY (nb) OF TOTAL BAND WEIGHTS
        """
        nb = self.procar["header"]["bands"]
        nion = self.procar["header"]["ions"]
        orbs = self.procar["header"]["orbitals"]
        weights = [[{orb: 0.0 for orb in orbs} for _ in range(nion)] for _ in range(nb)]
        band_weights = [0.0 for _ in range(nb)]
        for kp in self.procar["kpoints"]:
            for band in kp["bands"]:
                b_idx = band["index"] - 1
                for ion in band["ions"]:
                    i_idx = ion["index"] - 1
                    for orb in orbs:
                        weights[b_idx][i_idx][orb] += ion[orb]
                band_weights[b_idx] += band["total"]["total"]
        return np.array(weights, dtype=object), band_weights
    
    
    def compute_per_kpoint_weights(self):
        if self._per_kpoint_weights is not None:
            return self._per_kpoint_weights

        nb = self.procar["header"]["bands"]
        nk = self.procar["header"]["kpoints"]
        nion = self.procar["header"]["ions"]
        orbs = self.procar["header"]["orbitals"]
        norb = len(orbs)

        per_k = np.zeros((nb, nk, nion, norb), dtype=float)
        per_k_totals = np.zeros((nb, nk), dtype=float)

        for k_idx, kp in enumerate(self.procar["kpoints"]):
            for band in kp["bands"]:
                b_idx = band["index"] - 1
                for ion in band["ions"]:
                    i_idx = ion["index"] - 1
                    for o_idx, orb in enumerate(orbs):
                        val = float(ion[orb])
                        per_k[b_idx, k_idx, i_idx, o_idx] = val
                        per_k_totals[b_idx, k_idx] += val
                
        self._per_kpoint_weights = (per_k, per_k_totals)
        return self._per_kpoint_weights
        
    def compute_per_kpoint_selected_weights(self, selected_ions, selected_orbs):
        per_k, per_k_totals = self.compute_per_kpoint_weights()
        nb, nk = per_k.shape[0], per_k.shape[1]

        orb_idx_set = {self._orb_index[o] for o in selected_orbs if o in self._orb_index}
        ion_set = set(selected_ions)

        selected_per_k = np.zeros((nb, nk), dtype = float)

        for b in range(nb):
            for k in range(nk):
                for i in range(per_k.shape[2]):
                    if i+1 in ion_set:
                        for oi in orb_idx_set:
                            selected_per_k[b, k] += per_k[b, k, i, oi]
        
        return selected_per_k, per_k_totals

    #---------------FATBAND IDENTIFICATION---------------
    def identify_fatbands(self):
        """
        Returns (fatbands, min_max_energies)
        - fatbands: array of dicts {"E-min", "E-max", "bands": [band_indices]}
        - min_max_energies: array [[emin, emax] for each band index]
        """
        min_max_energies = []
        fatbands = []
        for band in self.energies:
            min_max_energies.append([float(np.min(band)), float(np.max(band))])
        
        for i, band in enumerate(min_max_energies):
            placed = False
            # Check current fatbands
            for fatband in fatbands:
                # If any part of band IN fatband:
                if ((fatband["E-min"] <= band[0] <= fatband["E-max"]) or
                    (fatband["E-min"] <= band[1] <= fatband["E-max"]) or
                    (band[0] < fatband["E-min"] and band[1] > fatband["E-max"])):
                    # Then add band to fatband and update it
                    fatband["bands"].append(i)
                    fatband["E-min"] = min(band[0], fatband["E-min"])
                    fatband["E-max"] = max(band[1], fatband["E-max"])
                    placed = True
                    break
            
            # If unsorted, make new fatband
            if not placed:
                fatbands.append({
                    "E-min": band[0],
                    "E-max": band[1],
                    "bands": [i]
                })

        return fatbands, min_max_energies
    
    # ---------------- FATBAND INFO -------------------
    def fatband_info(self, fatband, min_max_energies=None, top_n=3):
        """
        returns sorted array of dicts for bands in fatband['bands']
        band: {"index" "E-min" "E-max" "top3" "top_weight"}
        topk = [cont1 cont2 cont3 ...]
        cont = {"ion" "orbital" "weight"}
        """

        if min_max_energies is None:
            _, min_max_energies = self.identify_fatbands()

        fatband_info = []
        # FOR EACH BAND LISTINDEX IN FATBAND
        for b_idx in fatband["bands"]:
            contributions = []
            # CREATE DICTIONARY OF WEIGHTS BY ION/ORB
            for i_idx, ion in enumerate(weights[b_idx]):
                for orb, weight in ion.items():
                    contributions.append({
                        "ion": i_idx+1,
                        "orbital": orb,
                        "weight": weight
                        })
            # TOP CONTRIBUTIONS IN BAND
            topk = sorted(contributions, key=lambda x: x["weight"], reverse=True)[:top_n]
            top_weight = topk[0]["weight"] if topk else 0.0
            # ADD INFO TO FATBAND_INFO
            fatband_info.append({
                "index": b_idx + 1,
                "E-min": min_max_energies[b_idx][0],
                "E-max": min_max_energies[b_idx][1],
                f"top{top_n}": topk,
                "top_weight": top_weight
            })

        fatband_info_list = sorted(fatband_info, key=lambda x: x["top_weight"], reverse=True)
        return fatband_info_list
    

    def get_band_from_list(self, fatband_info_list, index):
        for b in fatband_info_list:
            if b["index"] == index:
                return b
        return None

    #------------------- selection helpers ------------------
    
    def compute_selected_weights(self, selected_ions, selected_orbs):
        """GIVES ARRAY OF WEIGHTS PER BAND (Selected ions/orbitals only and total)
        selected weights = array (nb) - same shape as band_weights
        """
        nb = len(self.weights)
        selected_weights = np.zeros(nb)
        for b_idx in range(nb):
            band_sel = 0.0
            for i_idx, ion in enumerate(self.weights[b_idx]):
                for orb, w in ion.items():
                    if (i_idx+1) in selected_ions and orb in selected_orbs:
                        band_sel += float(w)
            selected_weights[b_idx] = band_sel
        return selected_weights
    

    def get_selected_weights_in_window_approx(self, ymin, ymax, selected_ions, selected_orbs):
        """ 
        compute selected-orbital weight included within window 
        APPROX: proportion of band within energy window * band selected weight
        fraction_of_band_energy_range_in_window = overlap_length / (emax-emin)
        """
        bands_in_window = self.get_bands_in_window(ymin, ymax)
        selected_weights = self.compute_selected_weights(selected_ions, selected_orbs)
        sel_weight_in_window = 0.0
        for b in bands_in_window:
            emin = self.energies[b].min(); emax = self.energies[b].max()
            if emax - emin < 1e-9:
                overlap_frac = 1.0 if (emin>=ymin and emin<=ymax) else 0.0
            else:
                overlap_low = max(emin, ymin)
                overlap_high = min(emax, ymax)
                overlap_len = max(0.0, overlap_high - overlap_low)
                overlap_frac = overlap_len / (emax - emin)
            sel_weight_in_window += selected_weights[b] * overlap_frac

    def get_selected_weights_in_window_exact(self, ymin, ymax, selected_ions, selected_orbs):
        """ 
        compute selected-orbital weight included within window 
        EXACT: per k-point basis
        """
        per_k, per_k_totals = self.compute_per_kpoint_weights() # (nb,nk,nion,norn), (nb,nk)
        nb, nk = per_k.shape[0], per_k.shape[1]
        sel_weight_in_window = 0.0
        weight_in_window = 0.0

        orb_idx_set = {self._orb_index[o] for o in selected_orbs if o in self._orb_index}
        ion_set = set(selected_ions)

        for b in range(nb):
            for k in range(nk):
                E = float(self.energies[b, k]) # Energy of b at k
                if ymin <= E <= ymax:
                    for i in range(per_k.shape[2]): # Sum over ion list-indices
                        if (i+1) in ion_set: # If ion index is listed
                            for oi in orb_idx_set:
                                sel_weight_in_window += per_k[b, k, i, oi]
                        else:
                            for o, oi in self._orb_index:
                                weight_in_window += per_k[b,k,i,oi]
        
        return sel_weight_in_window, weight_in_window

    #----------------- Misc helpers --------------------------------

    def get_bands_in_window(self, ymin, ymax):
        """ GIVES LIST-INDICES OF BANDS IN WINDOW [int]"""
        bands_in_window = []
        for b_idx in range(len(self.energies)):
            emin = energies[b_idx].min()
            emax = energies[b_idx].max()
            if not (emax < ymin or emin > ymax):
                bands_in_window.append(b_idx)
        return bands_in_window
  
# ================================= BANDSTRUCTURE PLOTTING FUNCTION ====================================

def plot_bandstructure(bd, fermi=0.0, fatband=None, selected_ions=None, selected_orbs=None,
                       colormap='plasma', linewidth_scale=2.0):
    """PLOTS ENTIRE BANDSTRUCTURE OR FATBAND"""

    # Sets selection to all if none
    if selected_ions is None:
        selected_ions = list(range(1, bd.procar["header"]["ions"]+1))
    if selected_orbs is None:
        selected_orbs = bd.procar["header"]["orbitals"]

    # Gives selected weights and total weights at every kpoint - (nb nk)
    selected_per_k, total_per_k = bd.compute_per_kpoint_selected_weights(selected_ions, selected_orbs)
    # Transforms this into proportion at every kpoint - (nb, nk)
    prop_per_k = np.divide(selected_per_k, total_per_k,
                           out=np.zeros_like(selected_per_k), where=total_per_k!=0)
    
    print(total_per_k)
    print(selected_per_k)

    # Normalising total weight - (nb, nk)
    max_total = np.max(total_per_k)
    min_total = np.min(total_per_k)
    norm_total = (total_per_k - min_total)/(max_total-min_total + 1e-12)

    fig, ax = plt.subplots(figsize=(10,6))

    # Creating array of kpoints (nk)
    nk = bd.procar["header"]["kpoints"]
    k_indices = np.arange(nk)

    cmap = plt.get_cmap(colormap)

    # Looping through all bands
    for b_idx in range(bd.energies.shape[0]):
        # Fermi-shifted energies in a band (nk)
        y = bd.energies[b_idx] - fermi
        # Band selection proprtion (nk)
        prop = prop_per_k[b_idx]
        # Band weight (nk)
        weight = norm_total[b_idx]
        #print(weight)
        
        # Creates points of energy in a band... ([1 E1], [2 E2], [3 E3], ..., [N EN])
        points = np.array([k_indices, y]).T.reshape(-1, 1, 2)
        # Creates line segments... [not sure what shape]
        segments = np.concatenate([points[:-1], points[1:]], axis=1)

        # compute per-segment values
        avg_props = 0.5*(prop[:-1] + prop[1:])
        avg_lws   = np.maximum(linewidth_scale * 0.5*(weight[:-1] + weight[1:]), 0)

        seg_colors = cmap(avg_props)

        # lc = LineCollection(segments, linewidths=avg_lws, colors = seg_colors)
        
        lc = LineCollection(segments, cmap=cmap, norm=Normalize(0,1), linewidths=avg_lws)
        lc.set_array(prop)
        ax.add_collection(lc)

    sm = plt.cm.ScalarMappable(cmap=cmap)
    sm.set_array([])
    cbar = plt.colorbar(sm, ax=ax)
    cbar.set_label('Proportion of selected orbital weight')

    if fatband:
        ax.set_ylim(fatband["E-min"] - fermi, fatband["E-max"] - fermi)
        
    ax.axhline(0.0, color='red', linestyle='--', linewidth=1, label='E_F')
    ax.set_xlabel('k-point index')
    ax.set_ylabel('Energy (eV relative to E_F)')
    ax.set_xlim(0, nk-1)
    ax.legend()
    
    print(f"Number of collections: {len(ax.collections)}")

    print(ax)
    plt.tight_layout()
    plt.show()

# ======================================= INTERACTIVE BANDSTRUCTURE WINDOW ====================================
def interactive_procar_ui(procar, energies, weights, total_weights, fermi=0.0, fatband=None):
    
    # Number of bands, kpoints, ions, orbitals
    nb, nk = procar["header"]["bands"], procar["header"]["kpoints"]
    ion_count = procar["header"]["ions"]
    orbitals = procar["header"]["orbitals"]

    # Default highlight threshold
    highlight_threshold = 0.1

    # Figure layout
    fig = plt.figure(figsize=(12,7))
    ax_main = fig.add_axes([0.05, 0.12, 0.62, 0.82]) # Main Band Plot
    ax_orbit = fig.add_axes([0.72, 0.60, 0.1, 0.32]) # Orbital Checkboxes
    ax_ions = fig.add_axes([0.93, 0.12, 0.07, 0.80])   # ions checkboxes (vertical)
    ax_text = fig.add_axes([0.72, 0.12, 0.15, 0.36])   # stats text
    ax_slider = fig.add_axes([0.1, 0.015, 0.4, 0.04])  # threshold slider
    ax_soc = fig.add_axes([0.55, 0.015, 0.08, 0.04])    # SOC button

    # Turn off axes for non-plot areas
    ax_orbit.axis('off')
    ax_ions.axis('off')
    ax_text.axis('off')

    # Main plot setup
    ax_main.set_title("Bandstructure (select orbitals/ions on right)")
    ax_main.set_xlabel("k-point index")
    ax_main.set_ylabel("Energy (eV relative to E_F)")
    ax_main.axhline(0.0, color='red', linestyle='--', linewidth=1, zorder=2) # Fermi energy line

    # Choose ylimits based on fatband and fermi energy
    if fatband is not None:
        ax_main.set_ylim(fatband["E-min"] - fermi, fatband["E-max"] - fermi)

    # create checkboxes for orbitals
    orb_labels = [o for o in orbitals]
    orb_initial = [False]*len(orb_labels)
    orbit_cb = CheckButtons(ax_orbit, orb_labels, orb_initial)

    # create checkboxes for ions 
    ion_labels = [f"I{ii}" for ii in range(1, ion_count+1)]
    ion_initial = [False]*len(ion_labels)
    ion_cb = CheckButtons(ax_ions, ion_labels, ion_initial)

    # SOC toggle (single checkbox)
    soc_cb = CheckButtons(ax_soc, ['SOC'], [False])

    # slider for highlight threshold (fraction)
    slider = Slider(ax_slider, "Threshold", 0.0, 1.0, valinit=highlight_threshold)

    # draggable lines: start around fermi±1 eV
    top_line = DraggableHLine(ax_main, +1.0, color='cyan', linestyle='-')
    bot_line = DraggableHLine(ax_main, -1.0, color='cyan', linestyle='-')

    # secondary y-axis for absolute energy
    def rel_to_abs(E_rel): return E_rel+fermi
    def abs_to_rel(E_abs): return E_abs-fermi
    secax = ax_main.secondary_yaxis('right', functions=(rel_to_abs, abs_to_rel))
    secax.set_ylabel("Energy (eV, absolute)")

    # store plotted artists to clear them as needed
    plotted_lines = []
    shaded_patch = None

    # helper to get current projection selections
    def get_current_selection():
        s_orbs = [lab for lab, val in zip(orb_labels, orbit_cb.get_status()) if val]
        s_ions = [i+1 for i, val in enumerate(ion_cb.get_status()) if val]
        soc_state = soc_cb.get_status()[0]
        return s_ions, s_orbs, soc_state

    # Function to calculate and update stats text
    def update_stats_and_text(selected_ions_list, selected_orbs_list, sel_weights, total_sel_weight_window, total_weight_window, window_band_idxs, y_min_rel, y_max_rel):
        
        # compute wannier_count as (#selected ions * selected orbitals * (2 if soc else 1))
        wannier_count = len(selected_ions_list) * len(selected_orbs_list) * (2 if soc_cb.get_status()[0] else 1)
        # compute number of bands in window
        bands_in_window = len(window_band_idxs)

        # percentage of total selected weight included in window
        total_selected_weight_allbands = sel_weights.sum()
        pct_in_window = (total_sel_weight_window / total_selected_weight_allbands * 100.0) if total_selected_weight_allbands > 0 else 0.0

        """IMPROVEMENT: Show in-band weights only rather than weights of entire band if any part in window"""
        # summary of top contributing ions/orbitals outside selection within window
        # compute contribution matrix for window
        other_contribs = {}
        for b in window_band_idxs:
            for i_idx, ion in enumerate(weights[b]):
                for orb, w in ion.items():
                    if (i_idx+1) not in selected_ions_list or orb not in selected_orbs_list:
                        key = f"I{i_idx+1}:{orb}"
                        other_contribs[key] = other_contribs.get(key, 0.0) + w
        # sort top 5 other contributors
        top_other = sorted(other_contribs.items(), key=lambda x: x[1], reverse=True)[:5]

        # compose text
        lines = [
            f"Wannier functions: {wannier_count}",
            f"Bands in window: {bands_in_window}",
            "",
            f"Total weight in window:\n {total_weight_window:.4f}",
            f"Selected weight in window:\n {total_sel_weight_window:.4f}",
            f"% of selected weight in window:\n {pct_in_window:.2f}%",
            "",
            f"Window (relative):\n{y_min_rel:.3f} -> {y_max_rel:.3f} eV",
            f"Window (absolute):\n{y_min_rel+fermi:.3f} -> {y_max_rel+fermi:.3f} eV",
            "",
            "Top other contributors in window:"
        ]
        # Add top other contributors to text
        if top_other:
            for k, v in top_other:
                lines.append(f"  {k}: {v:.4f}")
        else:
            lines.append("  None")

        # update text box
        ax_text.clear()
        ax_text.axis('off')
        ax_text.text(0, 0.95, "\n".join(lines), va='top', fontsize=8, family='monospace')

    # Main update function to redraw plot based on selections
    def update_plot(event=None):

        # clear previous lines and shaded patches
        nonlocal plotted_lines, shaded_patch
        for ln in plotted_lines:
            try:
                ln.remove()
            except:
                pass
        plotted_lines = []
        if shaded_patch is not None:
            try:
                shaded_patch.remove()
            except Exception:
                pass
            shaded_patch = None

        # read selections
        s_ions, s_orbs, soc_state = get_current_selection()


        # compute per-band weights and selected weights
        sel_band_weights = np.zeros(len(weights))
        band_total_weights = np.zeros(len(weights))
        for b in range(len(weights)):                   # Iterate over all bands
            band_sel = 0.0
            band_tot = 0.0
            for i_idx, ion in enumerate(weights[b]):    # Iterate over all ions in band
                for orb, w in ion.items():              # Iterate over all orbitals in ion
                    band_tot += w                       # Add to total weight for band
                    if (i_idx+1) in s_ions and orb in s_orbs: # If ion and orbital are selected
                        band_sel += w                   # Add to selected weight for band
            sel_band_weights[b] = band_sel
            band_total_weights[b] = band_tot if band_tot>0 else 1e-12
        # compute per-band fraction (selected fraction)
        frac = sel_band_weights / band_total_weights

        # determine window indices by energy (Relative to fermi)
        ytop = top_line.get_y()
        ybot = bot_line.get_y()
        ymin = min(ytop, ybot)
        ymax = max(ytop, ybot)

        # find band indices that have any energy within window (use min_max_energies)
        bands_in_window = []
        for b_idx in range(len(energies)):
            emin = energies[b_idx].min()   
            emax = energies[b_idx].max()
            if not ((emax - fermi) < ymin or (emin - fermi) > ymax): # Absolute energies converted to relative
                bands_in_window.append(b_idx)

        """ IMPROVEMENT: Option for exact per-kpoint weight calculation in window """
        # Approximate weights in window using overlap fraction
        sel_weight_in_window = 0.0
        weight_in_window = 0.0
        for b in bands_in_window:
            emin = energies[b].min(); emax = energies[b].max()
            if emax - emin < 1e-9:
                overlap_frac = 1.0 if (emin>=ymin and emin<=ymax) else 0.0
            else:
                overlap_low = max(emin, ymin)
                overlap_high = min(emax, ymax)
                overlap_len = max(0.0, overlap_high - overlap_low)
                overlap_frac = overlap_len / (emax - emin)
            sel_weight_in_window += sel_band_weights[b] * overlap_frac
            weight_in_window += band_total_weights[b] * overlap_frac


        shaded_patch = ax_main.axhspan(ymin, ymax, color='yellow', alpha=0.12, zorder=5)

        # plot
        nk_idx = np.arange(nk)
        max_total = max(total_weights) if len(total_weights)>0 else 1.0
        min_total = min(total_weights) if len(total_weights)>0 else 0.0

        for b_idx in range(len(energies)):
            band_y = energies[b_idx] - fermi  # relative energies

            # linewidth + alpha from total_weights
            w = total_weights[b_idx] if total_weights is not None else 1.0
            norm_w = (w - min_total) / (max_total - min_total + 1e-12)
            lw = norm_w
            alpha = 0.2 + 0.8*norm_w

            # highlight bands with high selected fraction
            is_highlight = frac[b_idx] >= slider.val
            if is_highlight:
                color='red'
            else:
                color='black'

            # plot continuous line (single color)
            ln, = ax_main.plot(nk_idx, band_y, color, linewidth=lw, alpha=alpha, zorder=2)
            plotted_lines.append(ln)

        # ensure draggable lines are above everything
        top_line.line.set_zorder(100)
        bot_line.line.set_zorder(100)
        if top_line.text: top_line.text.set_zorder(101)
        if bot_line.text: bot_line.text.set_zorder(101)

        # update side-panel stats
        update_stats_and_text(s_ions, s_orbs, sel_band_weights, sel_weight_in_window, weight_in_window, bands_in_window, ymin, ymax)

        # update main canvas
        ax_main.relim(); ax_main.autoscale_view()
        ax_main.set_xlim(0, nk-1)
        ax_main.figure.canvas.draw_idle()

    # hook callbacks
    orbit_cb.on_clicked(lambda label: update_plot())
    ion_cb.on_clicked(lambda label: update_plot())
    soc_cb.on_clicked(lambda label: update_plot())
    slider.on_changed(lambda val: update_plot())
    top_line.on_change_callback = update_plot
    bot_line.on_change_callback = update_plot

    # initial draw
    update_plot()
    plt.show()

"""
def interactive_procar_ui(band_data):
    #Interactive UI for exploring PROCAR data using integrated BandData class
    
    bd = band_data
    procar = bd.procar
    nb, nk = procar["header"]["bands"], procar["header"]["kpoints"]
    ion_count = procar["header"]["ions"]
    orbitals = procar["header"]["orbitals"]
    fermi = bd.fermi
    
    highlight_threshold = 0.1
    
    fig = plt.figure(figsize=(14,8))
    ax_main = fig.add_axes([0.05, 0.12, 0.58, 0.82]) # Main Band Plot
    ax_orbit = fig.add_axes([0.68, 0.60, 0.12, 0.32]) # Orbital Checkboxes
    ax_ions = fig.add_axes([0.82, 0.12, 0.08, 0.80])   # ions checkboxes (vertical)
    ax_text = fig.add_axes([0.68, 0.12, 0.22, 0.42])   # stats text
    ax_slider = fig.add_axes([0.1, 0.015, 0.3, 0.04])  # threshold slider
    ax_soc = fig.add_axes([0.45, 0.015, 0.08, 0.04])    # SOC button

    ax_orbit.axis('off')
    ax_ions.axis('off')
    ax_text.axis('off')
    ax_main.set_title("Bandstructure (select orbitals/ions on right)")
    ax_main.set_xlabel("k-point index")
    ax_main.set_ylabel("Energy (eV relative to E_F)")
    ax_main.axhline(0.0, color='red', linestyle='--', linewidth=1, zorder=2)

    # create checkboxes for orbitals
    orb_labels = [o for o in orbitals]
    orb_initial = [False]*len(orb_labels)
    orbit_cb = CheckButtons(ax_orbit, orb_labels, orb_initial)

    # create checkboxes for ions 
    ion_labels = [f"I{ii}" for ii in range(1, ion_count+1)]
    ion_initial = [False]*len(ion_labels)
    ion_cb = CheckButtons(ax_ions, ion_labels, ion_initial)

    # SOC toggle (single checkbox)
    soc_cb = CheckButtons(ax_soc, ['SOC'], [False])

    # slider for highlight threshold (fraction)
    slider = Slider(ax_slider, "Threshold", 0.0, 1.0, valinit=highlight_threshold)

    # draggable lines: start around fermi±1 eV
    top_line = DraggableHLine(ax_main, fermi + 1.0, color='cyan', linestyle='-')
    bot_line = DraggableHLine(ax_main, fermi - 1.0, color='cyan', linestyle='-')

    def rel_to_abs(E_rel): return E_rel+fermi
    def abs_to_rel(E_abs): return E_abs-fermi
    secax = ax_main.secondary_yaxis('right', functions=(rel_to_abs, abs_to_rel))
    secax.set_ylabel("Energy (eV, absolute)")

    # store plotted artists to clear them as needed
    plotted_lines = []
    shaded_patch = None

    def get_current_selection():
        # gather selections from widgets
        s_orbs = [lab for lab, val in zip(orb_labels, orbit_cb.get_status()) if val]
        s_ions = [i+1 for i, val in enumerate(ion_cb.get_status()) if val]
        soc_state = soc_cb.get_status()[0]
        return s_ions, s_orbs, soc_state

    def update_stats_and_text(selected_ions_list, selected_orbs_list, y_min_rel, y_max_rel):
        # Use BandData methods for accurate calculations
        if selected_ions_list and selected_orbs_list:
            # Get exact weights in window using BandData method
            sel_weight_in_window, total_weight_window = bd.get_selected_weights_in_window_exact(
                y_min_rel + fermi, y_max_rel + fermi, selected_ions_list, selected_orbs_list
            )
            
            # Get total selected weights across all bands
            total_selected_weights = bd.compute_selected_weights(selected_ions_list, selected_orbs_list)
            total_selected_weight_allbands = total_selected_weights.sum()
            
            # Percentage of total selected weight in window
            pct_in_window = (sel_weight_in_window / total_selected_weight_allbands * 100.0) if total_selected_weight_allbands > 0 else 0.0
        else:
            sel_weight_in_window = 0.0
            total_weight_window = 0.0
            pct_in_window = 0.0
            total_selected_weight_allbands = 0.0
        
        # Get bands in window
        window_band_idxs = bd.get_bands_in_window(y_min_rel + fermi, y_max_rel + fermi)
        bands_in_window = len(window_band_idxs)

        # compute wannier_count as (#selected ions * #selected orbitals * (2 if soc else 1))
        wannier_count = len(selected_ions_list) * len(selected_orbs_list) * (2 if soc_cb.get_status()[0] else 1)

        # Summary of top contributing ions/orbitals outside selection within window
        other_contribs = {}
        if selected_ions_list and selected_orbs_list:
            for b in window_band_idxs:
                for i_idx, ion in enumerate(bd.weights[b]):
                    for orb, w in ion.items():
                        if (i_idx+1) not in selected_ions_list or orb not in selected_orbs_list:
                            key = f"I{i_idx+1}:{orb}"
                            other_contribs[key] = other_contribs.get(key, 0.0) + w
        
        # sort top 5 other contributors
        top_other = sorted(other_contribs.items(), key=lambda x: x[1], reverse=True)[:5]

        # compose text
        lines = [
            f"Wannier functions: {wannier_count}",
            f"Bands in window: {bands_in_window}",
            "",
            f"Total weight in window:",
            f"  {total_weight_window:.4f}",
            f"Selected weight in window:",
            f"  {sel_weight_in_window:.4f}",
            f"% of selected in window:",
            f"  {pct_in_window:.2f}%",
            "",
            f"Window (relative):",
            f"  {y_min_rel:.3f} -> {y_max_rel:.3f} eV",
            f"Window (absolute):",
            f"  {y_min_rel+fermi:.3f} -> {y_max_rel+fermi:.3f} eV",
            "",
            "Top other contributors:"
        ]
        if top_other:
            for k, v in top_other[:3]:  # Show only top 3 to save space
                lines.append(f"  {k}: {v:.4f}")
        else:
            lines.append("  None")

        ax_text.clear()
        ax_text.axis('off')
        ax_text.text(0, 0.95, "\n".join(lines), va='top', fontsize=8, family='monospace')

    def update_plot(event=None):
        # clear previous
        nonlocal plotted_lines, shaded_patch
        for ln in plotted_lines:
            try:
                ln.remove()
            except:
                pass
        plotted_lines = []

        if shaded_patch is not None:
            try:
                shaded_patch.remove()
            except Exception:
                pass
            shaded_patch = None

        # read selections
        s_ions, s_orbs, soc_state = get_current_selection()

        # Use BandData methods for weight calculations
        if s_ions and s_orbs:
            # Get per-kpoint selected weights and totals using BandData method
            selected_per_k, total_per_k = bd.compute_per_kpoint_selected_weights(s_ions, s_orbs)
            
            # compute per-band selected weights for band highlighting
            sel_band_weights = bd.compute_selected_weights(s_ions, s_orbs)
            
            # Compute fractions for highlighting
            total_band_weights = np.array([total_per_k[b].sum() for b in range(len(bd.energies))])
            total_band_weights = np.where(total_band_weights > 0, total_band_weights, 1e-12)
            frac = sel_band_weights / total_band_weights
        else:
            selected_per_k = np.zeros_like(bd.energies)
            total_per_k = np.ones_like(bd.energies)
            frac = np.zeros(len(bd.energies))

        # determine window indices by energy (use min/max y of lines)
        ytop = top_line.get_y()
        ybot = bot_line.get_y()
        ymin = min(ytop, ybot)
        ymax = max(ytop, ybot)

        # Add shaded region for energy window
        shaded_patch = ax_main.axhspan(ymin, ymax, color='yellow', alpha=0.12, zorder=1)

        # plot bands
        nk_idx = np.arange(nk)
        
        # Normalize total weights for linewidth scaling
        if total_per_k.size > 0:
            max_total = np.max(total_per_k)
            min_total = np.min(total_per_k)
        else:
            max_total = min_total = 1.0

        for b_idx in range(len(bd.energies)):
            band_y = bd.energies[b_idx] - fermi  # relative energies

            # linewidth from total weights (average across k-points)
            if total_per_k.size > 0:
                avg_weight = np.mean(total_per_k[b_idx])
                norm_w = (avg_weight - min_total) / (max_total - min_total + 1e-12)
                lw = 0.2 + 0.8 * norm_w  # scale linewidth
                alpha = 0.2 + 0.8 * norm_w
            else:
                lw = 1.0
                alpha = 0.8

            # highlight bands with high selected fraction
            is_highlight = frac[b_idx] >= slider.val
            if is_highlight:
                color = 'red'
            else:
                color = 'black'

            # plot continuous line
            ln, = ax_main.plot(nk_idx, band_y, color=color, linewidth=lw, alpha=alpha, zorder=2)
            plotted_lines.append(ln)

        # ensure draggable lines are above everything
        top_line.line.set_zorder(100)
        bot_line.line.set_zorder(100)
        if top_line.text: 
            top_line.text.set_zorder(101)
        if bot_line.text: 
            bot_line.text.set_zorder(101)

        # update side-panel stats
        update_stats_and_text(s_ions, s_orbs, ymin, ymax)

        # update main canvas
        ax_main.relim()
        ax_main.autoscale_view()
        ax_main.set_xlim(0, nk-1)
        ax_main.figure.canvas.draw_idle()

    # hook callbacks
    orbit_cb.on_clicked(lambda label: update_plot())
    ion_cb.on_clicked(lambda label: update_plot())
    soc_cb.on_clicked(lambda label: update_plot())
    slider.on_changed(lambda val: update_plot())
    top_line.on_change_callback = update_plot
    bot_line.on_change_callback = update_plot

    # initial draw
    update_plot()
    plt.show()
"""

if __name__ == "__main__":
    # PARSER OBJECT
    parser = Parser(procar_path="PROCAR", fermi_path="FERMI")
    procar = parser.procar
    fermi = parser.fermi
    print(f"FERMI ENERGY: {fermi}")

    # BAND_DATA OBJECT
    band_data = BandData(procar, fermi)
    energies = band_data.energies
    weights = band_data.weights
    total_weights = band_data.band_weights

    fatbands, minmax = band_data.identify_fatbands()

    fermi_fatband = None
    for fatband in fatbands:
        if fatband["E-min"] <= fermi <= fatband["E-max"]:
            fermi_fatband = fatband; break

    fatband_info = band_data.fatband_info(fermi_fatband, min_max_energies=minmax, top_n=3)
    print(fatband_info[:5])

    selected_ions = [26]
    selected_orbs = ['dxy', 'dyz', 'dz2', 'dxz', 'x2-y2']
    selected = band_data.compute_selected_weights(selected_ions, selected_orbs)

    print(band_data.energies.shape)   # is it (bands, kpoints) or (kpoints, bands)?

    plot_bandstructure(band_data, fermi, fatband=fermi_fatband,
                    selected_ions=selected_ions, selected_orbs=selected_orbs)

    print(total_weights)

    #interactive_procar_ui(band_data)
    interactive_procar_ui(procar, energies, weights, total_weights, fermi, fatband=fermi_fatband)
