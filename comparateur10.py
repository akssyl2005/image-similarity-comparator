import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import threading
import statistics
from functools import lru_cache

# ====================================================================
# SECTION 1 : CONSTANTES ET CONFIGURATION
# ====================================================================
# Paramètres d'analyse
GRID_SIZE = 20
WHITE_THRESHOLD = 210
CONTENT_RATIO_MIN = 0.35
BACKGROUND_WEIGHT = 0.0
EDGE_DETECTION = True
TEXTURE_DETECTION = False
EDGE_THRESHOLD = 8

# Palette de couleurs - NOUVEAU THÈME GRIS
BG_COLOR = "#1e1e1e"
BTN_COLOR = "#3d3d3d"
BTN_HOVER = "#4d4d4d"
ACCENT = "#0078d4"
TEXT_COLOR = "#ffffff"
PANEL_COLOR = "#2b2b2b"
SECONDARY_BG = "#3d3d3d"

# Formats d'image supportés
SUPPORTED_FORMATS = [
    ("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.tif *.ppm *.pgm *.pbm"),
    ("Tous les fichiers", "*.*")
]

# ====================================================================
# SECTION 2 : FONCTIONS UTILITAIRES DE TRAITEMENT D'IMAGE
# ====================================================================
@lru_cache(maxsize=256)
def parse_color_cached(c):
    """Version cachée pour éviter les conversions répétées"""
    if isinstance(c, str):
        c = c.strip()
        if c.startswith("#") and len(c) == 7:
            return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
        if c.isdigit():
            v = int(c)
            return (v, v, v)
    return (255, 255, 255)

def parse_color(c):
    """Convertit une couleur en tuple RGB"""  
    if isinstance(c, tuple) and len(c) == 3:
        return c
    return parse_color_cached(str(c))

@lru_cache(maxsize=512)
def luminance(rgb):
    """Calcule la luminance - version cachée"""
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b

@lru_cache(maxsize=512)
def is_white_pixel(rgb, threshold=WHITE_THRESHOLD):
    """Détecte si un pixel est blanc - version cachée"""
    r, g, b = rgb
    if r < threshold or g < threshold or b < threshold:
        return False
    avg = (r + g + b) / 3
    variance = ((r - avg)**2 + (g - avg)**2 + (b - avg)**2) / 3
    return variance < 15 and avg > threshold + 5

# ====================================================================
# SECTION 3 : FONCTIONS DE TRANSFORMATION D'IMAGE
# ====================================================================
def img_to_luminance_matrix_fast(img):
    """Version optimisée - traitement par bloc"""
    w, h = img.size
    
    # Convertir l'image PIL en données pixels
    pixels = img.load()
    
    # Pré-allouer les matrices
    mat = [[0.0]*w for _ in range(h)]
    white_mask = [[False]*w for _ in range(h)]
    
    # Traiter par lignes (meilleure localité cache)
    for y in range(h):
        for x in range(w):
            # PIL retourne un tuple RGB ou RGBA
            pixel = pixels[x, y]
            if len(pixel) == 4:  # RGBA
                rgb = pixel[:3]  # Ignorer alpha  
            else:  # RGB ou autre format
                rgb = pixel if len(pixel) >= 3 else (pixel, pixel, pixel)
            
            mat[y][x] = luminance(rgb)
            white_mask[y][x] = is_white_pixel(rgb) 
    
    return mat, white_mask

def detect_edges_optimized(mat):
    """Version optimisée de la détection de contours - Seulement sur échantillon"""
    h = len(mat)
    w = len(mat[0]) if h > 0 else 0
    edges = [[0.0] * w for _ in range(h)]
    
    # Échantillonnage : traiter 1 ligne sur 2 pour vitesse
    for y in range(1, h-1, 2):
        for x in range(1, w-1):
            gx = abs(mat[y][x+1] - mat[y][x-1])
            gy = abs(mat[y+1][x] - mat[y-1][x])
            edges[y][x] = (gx + gy) / 2
            # Copier sur la ligne suivante
            if y + 1 < h - 1:
                edges[y+1][x] = edges[y][x]
    
    return edges

def downscale_to_grid_fast(mat, white_mask, grid_size=GRID_SIZE):
    """Version ultra-optimisée avec calculs simplifiés"""
    h = len(mat)
    w = len(mat[0]) if h > 0 else 0
    if w == 0 or h == 0:
        return [[255.0]*grid_size for _ in range(grid_size)], [[False]*grid_size for _ in range(grid_size)]
    
    # Détection des contours seulement si activée
    edges = detect_edges_optimized(mat) if EDGE_DETECTION else None
    
    grid = [[255.0]*grid_size for _ in range(grid_size)]
    grid_has_content = [[False]*grid_size for _ in range(grid_size)]
    
    # Précalculer les limites pour chaque cellule
    cell_width = w / grid_size
    cell_height = h / grid_size
    
    for gy in range(grid_size):
        y0 = int(gy * cell_height)
        y1 = int((gy + 1) * cell_height)
        if y1 <= y0:
            y1 = y0 + 1
        
        for gx in range(grid_size):
            x0 = int(gx * cell_width)
            x1 = int((gx + 1) * cell_width)
            if x1 <= x0:
                x1 = x0 + 1
            
            content_values = []
            edge_count = 0
            total_pixels = (y1 - y0) * (x1 - x0)
            
            # Boucle optimisée
            for y in range(y0, y1):
                for x in range(x0, x1):
                    if not white_mask[y][x]:
                        content_values.append(mat[y][x])
                    
                    if EDGE_DETECTION and edges[y][x] > EDGE_THRESHOLD:
                        edge_count += 1
            
            content_ratio = len(content_values) / total_pixels if total_pixels > 0 else 0
            edge_ratio = edge_count / total_pixels if total_pixels > 0 else 0
            
            # Critères simplifiés
            has_content = (
                content_ratio >= CONTENT_RATIO_MIN or 
                (EDGE_DETECTION and edge_ratio > 0.12)
            )
            
            if has_content:
                if content_values:
                    grid[gy][gx] = sum(content_values) / len(content_values)
                else:
                    grid[gy][gx] = 128.0
                grid_has_content[gy][gx] = True
            else:
                grid[gy][gx] = 255.0
                grid_has_content[gy][gx] = False
    
    return grid, grid_has_content

# ====================================================================
# SECTION 4 : FONCTIONS DE TRAITEMENT DE GRILLE
# ====================================================================
def adaptive_threshold_fast(grid, content_mask):
    """Calcule un seuil adaptatif - version optimisée"""
    flat = [grid[y][x] for y in range(len(grid)) for x in range(len(grid[0])) if content_mask[y][x]]
    if not flat or len(flat) < 3:
        return 128
    
    # Utiliser seulement médiane et moyenne
    med = statistics.median(flat)
    mean = sum(flat) / len(flat)
    threshold = (0.5 * med + 0.5 * mean)
    return max(30, min(threshold, 220))

def grid_to_binary_fast(grid, content_mask):
    """Convertit la grille en binaire - version optimisée"""
    threshold = adaptive_threshold_fast(grid, content_mask)
    h, w = len(grid), len(grid[0])
    
    # Compréhension de liste plus rapide
    binary = [[1 if content_mask[y][x] and grid[y][x] < threshold else 0 
               for x in range(w)] for y in range(h)]
    
    return binary, content_mask

# ====================================================================
# SECTION 5 : TRANSFORMATIONS DE GRILLE
# ====================================================================
def rotate90_bin(grid, mask):
    return [list(row) for row in zip(*grid[::-1])], [list(row) for row in zip(*mask[::-1])]

def rotate180_bin(grid, mask):
    return [row[::-1] for row in grid[::-1]], [row[::-1] for row in mask[::-1]]

def rotate270_bin(grid, mask):
    g = [list(row) for row in zip(*grid)][::-1]
    m = [list(row) for row in zip(*mask)][::-1]
    return g, m

def flip_horizontal_bin(grid, mask):
    return [row[::-1] for row in grid], [row[::-1] for row in mask]

def flip_vertical_bin(grid, mask):
    return grid[::-1], mask[::-1]

# ====================================================================
# SECTION 6 : FONCTIONS DE COMPARAISON
# ====================================================================
def compare_binary_grids_fast(g1, mask1, g2, mask2):
    """Version ultra-optimisée de la comparaison - RETOURNE LES DÉTAILS"""
    h = len(g1)
    w = len(g1[0])
    
    # 1. COMPTEURS SIMPLES
    content_matches = 0
    content_cells = 0
    total_content1 = 0
    total_content2 = 0
    cx1, cy1, cx2, cy2 = 0, 0, 0, 0 
    
    # UNE SEULE BOUCLE pour tout calculer
    for y in range(h):
        for x in range(w):
            m1, m2 = mask1[y][x], mask2[y][x]
            
            if m1:
                total_content1 += 1
                cx1 += x
                cy1 += y
            
            if m2:
                total_content2 += 1
                cx2 += x
                cy2 += y
            
            if m1 and m2:
                content_cells += 1
                if g1[y][x] == g2[y][x]:
                    content_matches += 1
    
    # 2. CALCULS RAPIDES
    if content_cells == 0:
        return 0.0, {"content": 0.0, "shape": 0.0, "position": 0.0}
    
    content_similarity = (content_matches / content_cells) * 100.0
    
    # Position simplifiée
    if total_content1 > 0 and total_content2 > 0:
        center1 = (cx1 / total_content1, cy1 / total_content1)
        center2 = (cx2 / total_content2, cy2 / total_content2)
        center_distance = ((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)**0.5
        max_distance = (w**2 + h**2)**0.5
        center_similarity = max(0, 1 - (center_distance / max_distance)) * 100
    else:
        center_similarity = 0
    
    # Forme simplifiée (ratio de taille)
    if total_content1 > 0 and total_content2 > 0:
        shape_similarity = (min(total_content1, total_content2) / max(total_content1, total_content2)) * 100
    else:
        shape_similarity = 0
    
    # 3. CALCUL FINAL (pondération identique)
    final_similarity = (
        0.80 * content_similarity +
        0.12 * shape_similarity +
        0.08 * center_similarity
    )
    
    # 4. PÉNALITÉS SIMPLIFIÉES
    if total_content1 > 0 and total_content2 > 0:
        overlap_ratio = content_cells / max(total_content1, total_content2)
        if overlap_ratio < 0.7:
            final_similarity *= (overlap_ratio / 0.7)
        
        content_ratio = min(total_content1, total_content2) / max(total_content1, total_content2)
        if content_ratio < 0.85:
            final_similarity *= content_ratio
    
    if content_cells < 20:
        final_similarity *= (content_cells / 20)
    
    # Retourner le score final ET les détails
    details = {
        "content": content_similarity,
        "shape": shape_similarity,
        "position": center_similarity
    }
    
    return max(0.0, min(100.0, final_similarity)), details

# ====================================================================
# SECTION 7 : COMPOSANTS GRAPHIQUES
# ====================================================================
class StyledButton(tk.Button):
    """Bouton stylisé avec effet hover"""
    def __init__(self, master=None, bg=None, **kwargs):
        button_bg = bg if bg is not None else BTN_COLOR
        super().__init__(master, 
                         bg=button_bg, 
                         fg=TEXT_COLOR, 
                         activebackground=BTN_HOVER,
                         activeforeground=TEXT_COLOR, 
                         font=("Segoe UI", 11, "bold"),
                         relief="flat", 
                         bd=0, 
                         padx=12, 
                         pady=8, 
                         cursor="hand2", 
                         **kwargs)
        self.default_bg = button_bg
        self.bind("<Enter>", lambda e: self.config(bg=BTN_HOVER))
        self.bind("<Leave>", lambda e: self.config(bg=self.default_bg))

class ProgressBar(tk.Canvas):
    """Barre de progression personnalisée"""
    def __init__(self, master, width=200, height=20, **kwargs):
        super().__init__(master, width=width, height=height, bg=PANEL_COLOR, 
                        highlightthickness=0, **kwargs)
        self.width = width
        self.height = height
        self.value = 0
        
        # Dessiner le fond
        self.create_rectangle(0, 0, width, height, fill="#3d3d3d", outline="#555555")
        
        # Rectangle de progression
        self.progress_rect = self.create_rectangle(0, 0, 0, height, fill=ACCENT, outline="")
        
        # Texte
        self.text = self.create_text(width/2, height/2, text="0%", 
                                     fill=TEXT_COLOR, font=("Segoe UI", 9, "bold"))
    
    def set_value(self, value, color=None):
        """Met à jour la valeur de la barre"""
        self.value = max(0, min(100, value))
        progress_width = (self.value / 100) * self.width
        
        # Choisir la couleur selon la valeur
        if color is None:
            if self.value < 50:
                color = "#e74c3c"  # Rouge
            elif self.value < 70:
                color = "#f39c12"  # Orange
            else:
                color = "#27ae60"  # Vert
        
        self.itemconfig(self.progress_rect, fill=color)
        self.coords(self.progress_rect, 0, 0, progress_width, self.height)
        self.itemconfig(self.text, text=f"{self.value:.1f}%")

# ====================================================================
# SECTION 8 : APPLICATION PRINCIPALE
# ====================================================================
class ImageComparatorGridApp:
    """Application principale de comparaison d'images"""
    
    def __init__(self, root):
        self.root = root
        self.setup_window()
        self.init_variables()
        self.create_widgets()
        
    def setup_window(self):
        """Configure la fenêtre principale"""
        self.root.title("Comparaison d'images")
        self.root.geometry("1400x750")
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(True, True)
    
    def init_variables(self):
        """Initialise les variables d'instance"""
        self.photo1 = None
        self.photo2 = None
        self.pil_image1 = None
        self.pil_image2 = None
        self.lum1 = None
        self.lum2 = None
        self.mask1 = None
        self.mask2 = None
        self.scanning = False
        self.scan_step = 0
    
    def create_widgets(self):
        """Crée et positionne tous les widgets"""
        # Conteneur principal
        main_container = tk.Frame(self.root, bg=BG_COLOR)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Panneau gauche (contrôles et résultats)
        left_panel = self.create_left_panel(main_container)
        left_panel.pack(side="left", fill="y", padx=(0,10))
        left_panel.pack_propagate(False)
        
        # Panneau droit (affichage des images)
        right_panel = self.create_right_panel(main_container)
        right_panel.pack(side="left", fill="both", expand=True)
    
    def create_left_panel(self, parent):
        """Crée le panneau de contrôle gauche"""
        panel = tk.Frame(parent, bg=BG_COLOR, width=300)
        
        # Titre
        title = tk.Label(panel, text="🔍 Comparateur\nd'Images",
                         font=("Segoe UI", 16, "bold"), bg=BG_COLOR, fg=ACCENT, justify="center")
        title.pack(pady=(10,5))
        
        # Informations de méthodes
        info2 = tk.Label(panel, text=f"Analyse: 80% contenu\n12% forme + 8% position\nDétection: Contours optimisés",
                         font=("Segoe UI", 8), bg=BG_COLOR, fg="#aaaaaa", justify="center")
        info2.pack(pady=(0,15))
        
        # Formats supportés
        formats_info = tk.Label(panel, text=f"📁 Formats: PNG, JPG, GIF,\nBMP, TIFF, PPM, PGM, PBM",
                         font=("Segoe UI", 8), bg=BG_COLOR, fg="#00ffaa", justify="center")
        formats_info.pack(pady=(0,10))
        
        # Boutons de contrôle
        StyledButton(panel, text="📁 Charger image 1", command=self.load_image1).pack(pady=8, fill="x", padx=20)
        StyledButton(panel, text="📁 Charger image 2", command=self.load_image2).pack(pady=8, fill="x", padx=20)
        StyledButton(panel, text="🔍 Comparer", command=self.start_compare, bg=ACCENT).pack(pady=15, fill="x", padx=20)
        
        # Cadre des résultats
        results_frame = tk.Frame(panel, bg=PANEL_COLOR, relief="flat", bd=2)
        results_frame.pack(fill="both", expand=True, padx=10, pady=(10,10))
        
        results_title = tk.Label(results_frame, text="📊 Résultats",
                                font=("Segoe UI", 11, "bold"), bg=PANEL_COLOR, fg=TEXT_COLOR)
        results_title.pack(pady=(10,5))
        
        self.scan_label = tk.Label(results_frame, text="", font=("Segoe UI", 10), bg=PANEL_COLOR, fg="#bbbbbb", wraplength=250)
        self.scan_label.pack(pady=5)
        
        self.result_label = tk.Label(results_frame, text="Chargez deux images", font=("Segoe UI", 14, "bold"), 
                                     bg=PANEL_COLOR, fg=TEXT_COLOR, wraplength=250)
        self.result_label.pack(pady=10)
        
        self.detail_label = tk.Label(results_frame, text="", font=("Segoe UI", 8), bg=PANEL_COLOR, 
                                     fg="#cccccc", wraplength=250, justify="left")
        self.detail_label.pack(pady=5, padx=10)
        
        self.steps_text = tk.Label(results_frame, text="", font=("Segoe UI", 7), bg=PANEL_COLOR, 
                                   fg="#aaaaaa", wraplength=250, justify="left", anchor="w")
        self.steps_text.pack(pady=(10,10), padx=10, fill="x")
        
        return panel
    
    def create_right_panel(self, parent):
        """Crée le panneau d'affichage droit"""
        panel = tk.Frame(parent, bg=BG_COLOR)
        
        # Canvas avec scrollbar
        canvas = tk.Canvas(panel, bg=BG_COLOR, highlightthickness=0)
        scrollbar = tk.Scrollbar(panel, orient="vertical", command=canvas.yview)
        self.images_frame = tk.Frame(canvas, bg=BG_COLOR)
        
        canvas.create_window((0, 0), window=self.images_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.images_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Section des images originales
        tk.Label(self.images_frame, text="Images originales", font=("Segoe UI", 12, "bold"),
                bg=BG_COLOR, fg=ACCENT).grid(row=0, column=0, columnspan=2, pady=(10,5))
        
        self.thumb1 = tk.Label(self.images_frame, text="Image 1\n(cliquez pour charger)", 
                               bg=PANEL_COLOR, fg="#ffffff", relief="groove", bd=2, font=("Segoe UI", 9))
        self.thumb1.grid(row=1, column=0, padx=10, pady=10)
        
        self.thumb2 = tk.Label(self.images_frame, text="Image 2\n(cliquez pour charger)", 
                               bg=PANEL_COLOR, fg="#ffffff", relief="groove", bd=2, font=("Segoe UI", 9))
        self.thumb2.grid(row=1, column=1, padx=10, pady=10)
        
        # Section des grilles binaires
        tk.Label(self.images_frame, text="Grilles binaires (analyse)", font=("Segoe UI", 12, "bold"),
                bg=BG_COLOR, fg=ACCENT).grid(row=2, column=0, columnspan=2, pady=(20,5))
        
        self.thumb1_binary = tk.Label(self.images_frame, text="Grille 1", 
                                      bg=PANEL_COLOR, fg="#ffffff", relief="ridge", bd=2, font=("Segoe UI", 9))
        self.thumb1_binary.grid(row=3, column=0, padx=10, pady=10)
        
        self.thumb2_binary = tk.Label(self.images_frame, text="Grille 2", 
                                      bg=PANEL_COLOR, fg="#ffffff", relief="ridge", bd=2, font=("Segoe UI", 9))
        self.thumb2_binary.grid(row=3, column=1, padx=10, pady=10)
        
        # Section des barres de progression - À CÔTÉ
        tk.Label(self.images_frame, text="Métriques de similarité", font=("Segoe UI", 12, "bold"),
                bg=BG_COLOR, fg=ACCENT).grid(row=0, column=2, pady=(10,5), padx=(20,10))
        
        # Frame pour les barres de progression à côté des images
        progress_frame = tk.Frame(self.images_frame, bg=BG_COLOR)
        progress_frame.grid(row=1, column=2, rowspan=3, padx=(20,10), pady=10, sticky="n")
        
        # Barre Contenu (80%)
        tk.Label(progress_frame, text="Contenu (80%)", font=("Segoe UI", 10, "bold"),
                bg=BG_COLOR, fg=TEXT_COLOR, anchor="w").pack(fill="x", pady=(10,2))
        self.progress_content = ProgressBar(progress_frame, width=250, height=25)
        self.progress_content.pack(pady=(0,20))
        
        # Barre Forme (12%)
        tk.Label(progress_frame, text="Forme (12%)", font=("Segoe UI", 10, "bold"),
                bg=BG_COLOR, fg=TEXT_COLOR, anchor="w").pack(fill="x", pady=(5,2))
        self.progress_shape = ProgressBar(progress_frame, width=250, height=25)
        self.progress_shape.pack(pady=(0,20))
        
        # Barre Position (8%)
        tk.Label(progress_frame, text="Position (8%)", font=("Segoe UI", 10, "bold"),
                bg=BG_COLOR, fg=TEXT_COLOR, anchor="w").pack(fill="x", pady=(5,2))
        self.progress_position = ProgressBar(progress_frame, width=250, height=25)
        self.progress_position.pack(pady=(0,10))
        
        return panel
    
    # ====================================================================
    # SECTION 9 : MÉTHODES DE GESTION D'IMAGES
    # ====================================================================
    def load_generic(self):
        """Charge une image depuis le système de fichiers"""
        path = filedialog.askopenfilename(filetypes=SUPPORTED_FORMATS)
        if not path:
            return None, None, None
        try:
            # Ouvrir l'image avec PIL
            pil_img = Image.open(path)
            
            # Convertir en RGB si nécessaire
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            
            # Convertir PIL Image en PhotoImage pour Tkinter
            photo_img = ImageTk.PhotoImage(pil_img)
            
            return photo_img, pil_img, path
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger l'image :\n{e}")
            return None, None, None
    
    def make_thumb(self, path, label_widget, pil_image):
        """Crée une miniature d'image"""
        try:
            target_size = 150
            
            # Redimensionner l'image PIL
            pil_thumb = pil_image.copy()
            pil_thumb.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
            
            # Convertir en PhotoImage
            thumb_img = ImageTk.PhotoImage(pil_thumb)
            
            label_widget.config(image=thumb_img, text="")
            label_widget.image = thumb_img  # Garder une référence
        except Exception as e:
            label_widget.config(text=f"{path.split('/')[-1]}\n(erreur aperçu: {e})")
    
    def load_image1(self):
        """Charge la première image"""
        photo_img, pil_img, path = self.load_generic()
        if photo_img and pil_img:
            self.photo1 = photo_img
            self.pil_image1 = pil_img
            self.lum1, self.mask1 = img_to_luminance_matrix_fast(self.pil_image1)
            self.make_thumb(path, self.thumb1, self.pil_image1)
            if self.mask1:
                content_pixels = sum(1 for row in self.mask1 for cell in row if not cell)
                total_pixels = len(self.mask1) * len(self.mask1[0])
                content_percent = (content_pixels / total_pixels) * 100
                self.result_label.config(text=f"Image 1 chargée ✔️\n{content_percent:.1f}% contenu", fg=TEXT_COLOR)
    
    def load_image2(self):
        """Charge la deuxième image"""
        photo_img, pil_img, path = self.load_generic()
        if photo_img and pil_img:
            self.photo2 = photo_img
            self.pil_image2 = pil_img
            self.lum2, self.mask2 = img_to_luminance_matrix_fast(self.pil_image2)
            self.make_thumb(path, self.thumb2, self.pil_image2)
            if self.mask2:
                content_pixels = sum(1 for row in self.mask2 for cell in row if not cell)
                total_pixels = len(self.mask2) * len(self.mask2[0])
                content_percent = (content_pixels / total_pixels) * 100
                self.result_label.config(text=f"Image 2 chargée ✔️\n{content_percent:.1f}% contenu", fg=TEXT_COLOR)
    
    def show_binary_thumb(self, binary_grid, label_widget):
        """Affiche une miniature de la grille binaire"""
        h, w = len(binary_grid), len(binary_grid[0])
        scale = 7
        
        # Créer une image PIL pour la grille binaire
        img_pil = Image.new('RGB', (w*scale, h*scale), color='white')
        pixels = img_pil.load()
        
        for y in range(h):
            for x in range(w):
                color = (0, 0, 0) if binary_grid[y][x] else (255, 255, 255)
                for dy in range(scale):
                    for dx in range(scale):
                        pixels[x*scale + dx, y*scale + dy] = color
        
        # Convertir PIL en PhotoImage
        img_tk = ImageTk.PhotoImage(img_pil)
        
        label_widget.config(image=img_tk, text="")
        label_widget.image = img_tk  # Garder une référence
    
    # ====================================================================
    # SECTION 10 : MÉTHODES DE COMPARAISON
    # ====================================================================
    def animate_scan(self):
        """Animation pendant l'analyse"""
        if not self.scanning:
            return
        dots = "." * (self.scan_step % 4)
        self.scan_label.config(text=f"Analyse{dots}")
        self.scan_step += 1
        self.root.after(200, self.animate_scan)
    
    def start_compare(self):
        """Démarre la comparaison"""
        if not self.lum1 or not self.lum2:
            messagebox.showerror("Erreur", "Chargez les deux images avant de comparer.")
            return
        self.result_label.config(text="Analyse rapide...")
        self.detail_label.config(text="")
        self.steps_text.config(text="")
        self.scan_label.config(text="")
        
        # Réinitialiser les barres de progression
        self.progress_content.set_value(0)
        self.progress_shape.set_value(0)
        self.progress_position.set_value(0)
        
        self.scanning = True
        self.scan_step = 0
        self.animate_scan()
        t = threading.Thread(target=self.compare_worker, daemon=True)
        t.start()
    
    def compare_worker(self):
        """Traitement de comparaison en arrière-plan"""
        try:
            # Préparation des grilles
            grid1, content_mask1 = downscale_to_grid_fast(self.lum1, self.mask1, GRID_SIZE)
            grid2, content_mask2 = downscale_to_grid_fast(self.lum2, self.mask2, GRID_SIZE)
            content1 = sum(sum(row) for row in content_mask1)
            content2 = sum(sum(row) for row in content_mask2)
            
            # Conversion binaire
            bin1, mask1 = grid_to_binary_fast(grid1, content_mask1)
            bin2, mask2 = grid_to_binary_fast(grid2, content_mask2)
            
            # Affichage des miniatures
            self.root.after(0, lambda: self.show_binary_thumb(bin1, self.thumb1_binary))
            self.root.after(0, lambda: self.show_binary_thumb(bin2, self.thumb2_binary))
            
            # Informations sur l'optimisation
            steps_msg = (
                f"⚡ Optimisations:\n"
                f"• Grille réduite: {GRID_SIZE}×{GRID_SIZE}\n"
                f"• Cache LRU activé\n"
                f"• Texture désactivée\n"
                f"• 4 rotations testées"
            )
            self.root.after(0, lambda: self.steps_text.config(text=steps_msg))
            
            # Tests des transformations
            transforms = [
                (bin2, mask2, "Originale"),
                (rotate90_bin(bin2, mask2)[0], rotate90_bin(bin2, mask2)[1], "Rotation 90°"),
                (rotate180_bin(bin2, mask2)[0], rotate180_bin(bin2, mask2)[1], "Rotation 180°"),
                (rotate270_bin(bin2, mask2)[0], rotate270_bin(bin2, mask2)[1], "Rotation 270°")
            ]
            
            best = 0.0
            best_name = ""
            best_details = None
            
            for tgrid, tmask, name in transforms:
                sim, details = compare_binary_grids_fast(bin1, mask1, tgrid, tmask)
                if sim > best:
                    best = sim
                    best_name = name
                    best_details = details
            
            # Fin de l'analyse
            self.scanning = False
            self.root.after(0, lambda: self.scan_label.config(text=""))
            
            # Interprétation du résultat
            self.display_result(best, best_name, content1, content2, best_details)
            
        except Exception as e:
            self.scanning = False
            self.root.after(0, lambda: messagebox.showerror("Erreur", str(e)))
            self.root.after(0, lambda: self.scan_label.config(text=""))
            self.root.after(0, lambda: self.result_label.config(text="Erreur", fg="red"))
    
    def display_result(self, similarity, transformation, content1, content2, details):
        """Affiche le résultat de la comparaison"""
        if similarity < 25:
            interpretation = "Très différentes 🔴"
            color = "#ff6b6b"
        elif similarity < 50:
            interpretation = "Différentes 🟠"
            color = "#ffa500"
        elif similarity < 70:
            interpretation = "Moyennement similaires 🟡"
            color = "#ffd700"
        elif similarity < 85:
            interpretation = "Similaires 🟢"
            color = "#51cf66"
        else:
            interpretation = "Très similaires 💚"
            color = "#00d9ff"
        
        # Affichage du résultat principal
        self.result_label.config(text=f"Similarité:\n{similarity:.1f}%\n({transformation})", fg=color)
        
        # Détails supplémentaires
        detail_text = (f"{interpretation}\n"
                      f"Contenu img1: {content1}/{GRID_SIZE*GRID_SIZE}\n"
                      f"Contenu img2: {content2}/{GRID_SIZE*GRID_SIZE}")
        
        self.detail_label.config(text=detail_text)
        
        # Mettre à jour les barres de progression
        if details:
            self.progress_content.set_value(details["content"])
            self.progress_shape.set_value(details["shape"])
            self.progress_position.set_value(details["position"])

# ====================================================================
# SECTION 11 : POINT D'ENTRÉE
# ====================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = ImageComparatorGridApp(root)
    root.mainloop()