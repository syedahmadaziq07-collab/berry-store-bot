import React, { useState } from 'react';
import {
  Plus,
  Edit2,
  Trash2,
  CheckCircle2,
  XCircle,
  Eye,
  Smartphone,
  Sparkles,
  Package,
  Layers,
  ArrowRight,
  RefreshCw,
  FolderPlus,
  Save,
  X,
} from 'lucide-react';
import { Category, Product, ProductVariant } from '../types/store';
import { formatMYR, evaluateInventoryHealth } from '../utils/store-logic';

interface ShopManagementProps {
  categories: Category[];
  products: Product[];
  onSaveProduct: (prod: Partial<Product>) => Promise<void>;
  onDeleteProduct: (id: string) => Promise<void>;
  onAdjustStock: (id: string, newStock: number) => Promise<void>;
  onSaveCategory: (cat: Partial<Category>) => Promise<void>;
  onDeleteCategory: (id: string) => Promise<void>;
}

export const ShopManagement: React.FC<ShopManagementProps> = ({
  categories,
  products,
  onSaveProduct,
  onDeleteProduct,
  onAdjustStock,
  onSaveCategory,
  onDeleteCategory,
}) => {
  const [activeTab, setActiveTab] = useState<'products' | 'categories' | 'preview'>('products');
  const [selectedCategoryFilter, setSelectedCategoryFilter] = useState<string>('all');
  const [editingProduct, setEditingProduct] = useState<Partial<Product> | null>(null);
  const [isProductModalOpen, setIsProductModalOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<Partial<Category> | null>(null);
  const [isCategoryModalOpen, setIsCategoryModalOpen] = useState(false);

  // Stock edit popover state
  const [stockEditId, setStockEditId] = useState<string | null>(null);
  const [tempStockValue, setTempStockValue] = useState<number>(0);

  // Interactive Telegram simulator state
  const [simSelectedCat, setSimSelectedCat] = useState<string>('ENTERTAINMENT');
  const [simSelectedProd, setSimSelectedProd] = useState<Product | null>(null);
  const [simSelectedVariant, setSimSelectedVariant] = useState<ProductVariant | null>(null);
  const [simStep, setSimStep] = useState<'menu' | 'product_detail' | 'checkout_ready'>('menu');

  const filteredProducts = products.filter(p => {
    if (selectedCategoryFilter === 'all') return true;
    return p.category === selectedCategoryFilter;
  });

  const handleOpenAddProduct = () => {
    setEditingProduct({
      name: '',
      category: categories[0]?.name || 'ENTERTAINMENT',
      price: 15.00,
      stock: 10,
      duration: '1 Month',
      description: '',
      auto_delivery: true,
      is_active: true,
      delivery_type: 'automated',
      variants: [],
    });
    setIsProductModalOpen(true);
  };

  const handleOpenEditProduct = (p: Product) => {
    setEditingProduct({ ...p });
    setIsProductModalOpen(true);
  };

  const handleSaveProductSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingProduct?.name || editingProduct.price === undefined) return;
    await onSaveProduct(editingProduct);
    setIsProductModalOpen(false);
    setEditingProduct(null);
  };

  const handleOpenAddCategory = () => {
    setEditingCategory({
      name: '',
      emoji: '📁',
      description: '',
      display_order: categories.length + 1,
      is_active: true,
    });
    setIsCategoryModalOpen(true);
  };

  const handleSaveCategorySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCategory?.name) return;
    await onSaveCategory(editingCategory);
    setIsCategoryModalOpen(false);
    setEditingCategory(null);
  };

  return (
    <div className="space-y-6">
      {/* Header & Sub-Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-white font-display">Pengurusan Browse Shop Telegram</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Urus katalog produk, kategori, harga RM & pratonton bot Telegram secara langsung
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Tabs */}
          <div className="flex items-center bg-slate-900 border border-slate-800 p-1 rounded-xl">
            <button
              type="button"
              onClick={() => setActiveTab('products')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer flex items-center gap-1.5 ${
                activeTab === 'products' ? 'bg-pink-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              <Package className="w-3.5 h-3.5" />
              <span>Produk ({products.length})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('categories')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer flex items-center gap-1.5 ${
                activeTab === 'categories' ? 'bg-pink-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Kategori ({categories.length})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('preview')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer flex items-center gap-1.5 ${
                activeTab === 'preview' ? 'bg-pink-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              <Smartphone className="w-3.5 h-3.5" />
              <span>Telegram Bot Preview</span>
            </button>
          </div>

          {activeTab === 'products' && (
            <button
              type="button"
              onClick={handleOpenAddProduct}
              className="px-3 py-2 bg-pink-600 hover:bg-pink-500 text-white text-xs font-medium rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm"
            >
              <Plus className="w-4 h-4" />
              <span>Tambah Produk</span>
            </button>
          )}

          {activeTab === 'categories' && (
            <button
              type="button"
              onClick={handleOpenAddCategory}
              className="px-3 py-2 bg-pink-600 hover:bg-pink-500 text-white text-xs font-medium rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm"
            >
              <FolderPlus className="w-4 h-4" />
              <span>Tambah Kategori</span>
            </button>
          )}
        </div>
      </div>

      {/* PRODUCTS TAB */}
      {activeTab === 'products' && (
        <div className="space-y-4">
          {/* Category Filter Pills */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
            <span className="text-slate-400 shrink-0 font-medium">Tapis Kategori:</span>
            <button
              type="button"
              onClick={() => setSelectedCategoryFilter('all')}
              className={`px-3 py-1 rounded-lg transition-colors shrink-0 cursor-pointer ${
                selectedCategoryFilter === 'all'
                  ? 'bg-slate-800 text-white font-semibold border border-slate-700'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Semua ({products.length})
            </button>
            {categories.map(cat => (
              <button
                key={cat.id}
                type="button"
                onClick={() => setSelectedCategoryFilter(cat.name)}
                className={`px-3 py-1 rounded-lg transition-colors shrink-0 cursor-pointer flex items-center gap-1.5 ${
                  selectedCategoryFilter === cat.name
                    ? 'bg-pink-600/20 text-pink-300 font-semibold border border-pink-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>{cat.emoji}</span>
                <span>{cat.name}</span>
              </button>
            ))}
          </div>

          {/* Products Data Grid */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3">Produk & Butiran</th>
                    <th className="px-4 py-3">Kategori</th>
                    <th className="px-4 py-3 text-right">Harga (RM)</th>
                    <th className="px-4 py-3 text-center">Baki Stok</th>
                    <th className="px-4 py-3">Penghantaran</th>
                    <th className="px-4 py-3 text-center">Status Bot</th>
                    <th className="px-4 py-3 text-right">Tindakan</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-200">
                  {filteredProducts.map(p => {
                    const health = evaluateInventoryHealth(p.stock);
                    return (
                      <tr key={p.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-lg bg-slate-800 border border-slate-700 overflow-hidden shrink-0">
                              <img
                                src={p.image_url || '/images/berry_store_banner_1794372741684.jpg'}
                                alt={p.name}
                                className="w-full h-full object-cover"
                              />
                            </div>
                            <div>
                              <div className="font-semibold text-white">{p.name}</div>
                              <div className="text-[11px] text-slate-400 line-clamp-1 max-w-sm">
                                {p.description || 'Tiada deskripsi'}
                              </div>
                              {p.variants && p.variants.length > 0 && (
                                <div className="text-[10px] text-pink-400 mt-0.5">
                                  {p.variants.length} varian tersedia
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-slate-300 bg-slate-950 px-2 py-0.5 rounded border border-slate-800 text-[11px]">
                            {p.category}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono font-bold text-white tabular-nums">
                          {formatMYR(p.price)}
                          <div className="text-[10px] text-slate-400 font-sans font-normal">
                            {p.duration || 'Bulan'}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-center">
                          {stockEditId === p.id ? (
                            <div className="inline-flex items-center gap-1">
                              <input
                                type="number"
                                min="0"
                                value={tempStockValue}
                                onChange={e => setTempStockValue(Number(e.target.value))}
                                className="w-16 bg-slate-950 border border-pink-500 rounded px-1.5 py-0.5 text-center font-mono text-xs"
                                autoFocus
                              />
                              <button
                                type="button"
                                onClick={async () => {
                                  await onAdjustStock(p.id, tempStockValue);
                                  setStockEditId(null);
                                }}
                                className="p-1 text-emerald-400 hover:bg-slate-800 rounded"
                              >
                                <Save className="w-3.5 h-3.5" />
                              </button>
                              <button
                                type="button"
                                onClick={() => setStockEditId(null)}
                                className="p-1 text-slate-400 hover:bg-slate-800 rounded"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => {
                                setStockEditId(p.id);
                                setTempStockValue(p.stock);
                              }}
                              title="Klik untuk laras stok"
                              className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md font-mono font-semibold cursor-pointer border ${
                                health.status === 'out_of_stock'
                                  ? 'bg-red-500/15 text-red-300 border-red-500/30'
                                  : health.status === 'low_stock'
                                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                                  : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                              }`}
                            >
                              <span>{p.stock}</span>
                              <Edit2 className="w-2.5 h-2.5 opacity-60" />
                            </button>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-[11px] text-slate-300 flex items-center gap-1">
                            {p.auto_delivery ? (
                              <>
                                <Sparkles className="w-3 h-3 text-purple-400" />
                                <span>Automatik</span>
                              </>
                            ) : (
                              <span>Manual</span>
                            )}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-center">
                          <button
                            type="button"
                            onClick={() => onSaveProduct({ id: p.id, is_active: !p.is_active })}
                            className="inline-flex items-center cursor-pointer"
                            title={p.is_active ? 'Klik untuk nyahaktif' : 'Klik untuk aktif'}
                          >
                            {p.is_active ? (
                              <span className="flex items-center gap-1 text-[11px] text-emerald-400">
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                <span>Aktif</span>
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 text-[11px] text-slate-400">
                                <XCircle className="w-3.5 h-3.5" />
                                <span>Nyahaktif</span>
                              </span>
                            )}
                          </button>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              onClick={() => handleOpenEditProduct(p)}
                              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
                              title="Edit Produk"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => onDeleteProduct(p.id)}
                              className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors cursor-pointer"
                              title="Padam Produk"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* CATEGORIES TAB */}
      {activeTab === 'categories' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {categories.map(cat => {
            const catProds = products.filter(p => p.category === cat.name);
            return (
              <div key={cat.id} className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-2xl">{cat.emoji}</span>
                      <h3 className="font-bold text-white text-sm">{cat.name}</h3>
                    </div>
                    <span className={`text-[11px] px-2 py-0.5 rounded-full ${cat.is_active ? 'bg-emerald-500/15 text-emerald-400' : 'bg-slate-800 text-slate-400'}`}>
                      {cat.is_active ? 'Aktif' : 'Nyahaktif'}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mb-3">{cat.description || 'Tiada deskripsi khas.'}</p>
                  <div className="text-xs text-pink-400 font-medium">
                    {catProds.length} produk di bawah kategori ini
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs">
                  <span className="text-slate-400">Susunan: #{cat.display_order}</span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingCategory({ ...cat });
                        setIsCategoryModalOpen(true);
                      }}
                      className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors cursor-pointer"
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => onDeleteCategory(cat.id)}
                      className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* INTERACTIVE TELEGRAM SHOP PREVIEW */}
      {activeTab === 'preview' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <div className="max-w-md mx-auto">
            <div className="text-center mb-4">
              <h3 className="text-sm font-semibold text-white">Simulasi Paparan Pelanggan Telegram</h3>
              <p className="text-xs text-slate-400">
                Uji pengalaman Browse Shop pelanggan di Telegram bot secara interaktif
              </p>
            </div>

            {/* Simulated Telegram Chat Bubble */}
            <div className="bg-slate-950 border border-slate-800 rounded-3xl p-4 shadow-2xl space-y-3 font-sans">
              {/* Telegram Bot Header */}
              <div className="flex items-center gap-2.5 pb-2 border-b border-slate-800">
                <div className="w-7 h-7 rounded-full bg-pink-600 flex items-center justify-center text-white text-xs font-bold">
                  🍓
                </div>
                <div>
                  <div className="text-xs font-bold text-white leading-tight">Berry Store Bot</div>
                  <div className="text-[10px] text-emerald-400 leading-tight">bot · online</div>
                </div>
              </div>

              {/* Bot Message Body */}
              <div className="space-y-2">
                <div className="rounded-xl overflow-hidden border border-slate-800">
                  <img
                    src="/images/berry_store_banner_1794372741684.jpg"
                    alt="Berry Store"
                    className="w-full h-32 object-cover"
                  />
                </div>

                <div className="bg-slate-900/90 rounded-2xl p-3 border border-slate-800 text-xs text-slate-200 space-y-2">
                  <div className="font-semibold text-pink-300">
                    🍓 Selamat datang ke Berry Store Malaysia!
                  </div>
                  <p className="text-[11px] text-slate-300">
                    Pilih kategori di bawah untuk melihat akaun langganan premium dengan jaminan waranti automatik:
                  </p>

                  {/* Category Buttons inside Telegram Keyboard */}
                  <div className="grid grid-cols-2 gap-1.5 pt-1">
                    {categories.filter(c => c.is_active).map(cat => (
                      <button
                        key={cat.id}
                        type="button"
                        onClick={() => {
                          setSimSelectedCat(cat.name);
                          setSimSelectedProd(null);
                          setSimStep('menu');
                        }}
                        className={`py-2 px-2 text-center text-[11px] font-medium rounded-lg border transition-all cursor-pointer ${
                          simSelectedCat === cat.name
                            ? 'bg-pink-600/30 border-pink-500 text-white shadow-sm'
                            : 'bg-slate-800/90 border-slate-700/80 text-slate-200 hover:bg-slate-800'
                        }`}
                      >
                        {cat.emoji} {cat.name}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Products inside Selected Category */}
                <div className="bg-slate-900/80 rounded-2xl p-3 border border-slate-800 text-xs space-y-2">
                  <div className="text-[11px] font-bold text-slate-300 flex items-center justify-between">
                    <span>Senarai Produk: {simSelectedCat}</span>
                    <span className="text-pink-400 font-mono">
                      {products.filter(p => p.category === simSelectedCat && p.is_active).length} item
                    </span>
                  </div>

                  <div className="space-y-1.5">
                    {products
                      .filter(p => p.category === simSelectedCat && p.is_active)
                      .map(prod => (
                        <div
                          key={prod.id}
                          onClick={() => {
                            setSimSelectedProd(prod);
                            setSimSelectedVariant(prod.variants?.[0] || null);
                            setSimStep('product_detail');
                          }}
                          className={`p-2.5 rounded-xl border transition-all cursor-pointer flex items-center justify-between ${
                            simSelectedProd?.id === prod.id
                              ? 'bg-pink-500/20 border-pink-500 text-white'
                              : 'bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700'
                          }`}
                        >
                          <div>
                            <div className="font-semibold text-xs text-white">{prod.name}</div>
                            <div className="text-[10px] text-slate-400">
                              Stok: {prod.stock > 0 ? `${prod.stock} baki` : 'Habis'} · {prod.duration}
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-mono font-bold text-pink-400">{formatMYR(prod.price)}</div>
                            <span className="text-[10px] text-slate-400">Pilih &rsaquo;</span>
                          </div>
                        </div>
                      ))}
                  </div>
                </div>

                {/* Selected Product Detail / Purchase Dialog in Bot */}
                {simSelectedProd && (
                  <div className="bg-slate-900 border border-pink-500/40 rounded-2xl p-3 text-xs space-y-2.5 animate-in fade-in duration-200">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white text-xs">{simSelectedProd.name}</span>
                      <span className="font-mono font-bold text-pink-400">
                        {formatMYR(simSelectedVariant ? simSelectedVariant.price : simSelectedProd.price)}
                      </span>
                    </div>

                    <p className="text-[11px] text-slate-300">
                      {simSelectedProd.description}
                    </p>

                    {/* Variant selection buttons */}
                    {simSelectedProd.variants && simSelectedProd.variants.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-[10px] text-slate-400">Pilih Varian:</div>
                        <div className="grid grid-cols-2 gap-1.5">
                          {simSelectedProd.variants.map(v => (
                            <button
                              key={v.id}
                              type="button"
                              onClick={() => setSimSelectedVariant(v)}
                              className={`p-1.5 text-[11px] rounded border text-center transition-all ${
                                simSelectedVariant?.id === v.id
                                  ? 'bg-pink-600 text-white border-pink-500'
                                  : 'bg-slate-950 border-slate-800 text-slate-300'
                              }`}
                            >
                              <div>{v.variant_name}</div>
                              <div className="font-mono text-[10px] opacity-80">{formatMYR(v.price)}</div>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Instant Purchase Button */}
                    <button
                      type="button"
                      onClick={() => setSimStep('checkout_ready')}
                      className="w-full py-2 bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-500 hover:to-purple-500 text-white rounded-xl font-semibold text-xs flex items-center justify-center gap-1.5 shadow-md shadow-pink-600/30 cursor-pointer"
                    >
                      <span>🛒 Beli Sekarang via DuitNow QR</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ADD / EDIT PRODUCT MODAL */}
      {isProductModalOpen && editingProduct && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
              <h3 className="text-base font-bold text-white font-display">
                {editingProduct.id ? 'Kemaskini Produk' : 'Tambah Produk Baharu'}
              </h3>
              <button
                type="button"
                onClick={() => setIsProductModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveProductSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Nama Produk</label>
                <input
                  type="text"
                  required
                  value={editingProduct.name || ''}
                  onChange={e => setEditingProduct({ ...editingProduct, name: e.target.value })}
                  placeholder="e.g. Netflix Premium 4K UHD"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Kategori</label>
                  <select
                    value={editingProduct.category || ''}
                    onChange={e => setEditingProduct({ ...editingProduct, category: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
                  >
                    {categories.map(c => (
                      <option key={c.id} value={c.name}>{c.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Harga Standard (RM)</label>
                  <input
                    type="number"
                    step="0.50"
                    required
                    value={editingProduct.price ?? ''}
                    onChange={e => setEditingProduct({ ...editingProduct, price: Number(e.target.value) })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 font-mono focus:outline-none focus:border-pink-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Baki Stok</label>
                  <input
                    type="number"
                    min="0"
                    value={editingProduct.stock ?? 0}
                    onChange={e => setEditingProduct({ ...editingProduct, stock: Number(e.target.value) })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 font-mono focus:outline-none focus:border-pink-500"
                  />
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Tempoh Langganan</label>
                  <input
                    type="text"
                    value={editingProduct.duration || ''}
                    onChange={e => setEditingProduct({ ...editingProduct, duration: e.target.value })}
                    placeholder="e.g. 1 Month / 3 Months"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Deskripsi & Terma Jaminan</label>
                <textarea
                  rows={3}
                  value={editingProduct.description || ''}
                  onChange={e => setEditingProduct({ ...editingProduct, description: e.target.value })}
                  placeholder="Butiran produk dan arahan pengaktifan..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-100 focus:outline-none focus:border-pink-500"
                />
              </div>

              <div className="flex items-center gap-6 py-2">
                <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                  <input
                    type="checkbox"
                    checked={editingProduct.auto_delivery !== false}
                    onChange={e => setEditingProduct({ ...editingProduct, auto_delivery: e.target.checked })}
                    className="rounded border-slate-700 text-pink-600 focus:ring-pink-500"
                  />
                  <span>Penghantaran Kredensial Automatik</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                  <input
                    type="checkbox"
                    checked={editingProduct.is_active !== false}
                    onChange={e => setEditingProduct({ ...editingProduct, is_active: e.target.checked })}
                    className="rounded border-slate-700 text-pink-600 focus:ring-pink-500"
                  />
                  <span>Papar di Telegram Bot</span>
                </label>
              </div>

              <div className="pt-3 border-t border-slate-800 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsProductModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl transition-colors cursor-pointer"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-pink-600 hover:bg-pink-500 text-white rounded-xl font-medium transition-colors cursor-pointer"
                >
                  Simpan Produk
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ADD / EDIT CATEGORY MODAL */}
      {isCategoryModalOpen && editingCategory && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
              <h3 className="text-base font-bold text-white font-display">
                {editingCategory.id ? 'Kemaskini Kategori' : 'Tambah Kategori Baharu'}
              </h3>
              <button
                type="button"
                onClick={() => setIsCategoryModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveCategorySubmit} className="space-y-4 text-xs">
              <div className="grid grid-cols-4 gap-2">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Emoji</label>
                  <input
                    type="text"
                    value={editingCategory.emoji || ''}
                    onChange={e => setEditingCategory({ ...editingCategory, emoji: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-2 py-2 text-center text-lg focus:outline-none focus:border-pink-500"
                  />
                </div>
                <div className="col-span-3">
                  <label className="block text-slate-300 font-medium mb-1">Nama Kategori</label>
                  <input
                    type="text"
                    required
                    value={editingCategory.name || ''}
                    onChange={e => setEditingCategory({ ...editingCategory, name: e.target.value })}
                    placeholder="e.g. ENTERTAINMENT"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 uppercase focus:outline-none focus:border-pink-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Penerangan</label>
                <textarea
                  rows={2}
                  value={editingCategory.description || ''}
                  onChange={e => setEditingCategory({ ...editingCategory, description: e.target.value })}
                  placeholder="Penerangan ringkas kategori ini..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-100 focus:outline-none focus:border-pink-500"
                />
              </div>

              <div className="pt-3 border-t border-slate-800 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsCategoryModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl transition-colors cursor-pointer"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-pink-600 hover:bg-pink-500 text-white rounded-xl font-medium transition-colors cursor-pointer"
                >
                  Simpan Kategori
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
