from django.contrib import admin
from products.models import (
    Category, Supplier, Product,
    StockMovement,
    Transaction, TransactionItem,
    Payment,
    Purchase, PurchaseItem,
    SystemSetting
)


# ===========================
# 1. Category Admin
# ===========================
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']
    ordering = ['name']


# ===========================
# 2. Supplier Admin
# ===========================
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'address', 'created_at', 'updated_at']
    search_fields = ['name', 'phone']
    list_filter = ['created_at']
    ordering = ['name']
    readonly_fields = ['created_at', 'updated_at']


# ===========================
# 3. Product Admin
# ===========================
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'sku',
        'name',
        'category',
        'unit',
        'cost_price',
        'selling_price',
        'wholesale_price',
        'quantity',
        'min_stock',
        'is_bundle',
        'is_active'
    ]
    
    list_filter = [
        'is_active',
        'is_bundle',
        'category',
        'unit',
        'bundle_type'
    ]
    
    search_fields = [
        'sku',
        'name',
        'base_name',
        'compatible_models',
        'description'
    ]
    
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['sku']
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'sku',
                'name',
                'base_name',
                'description',
                'category',
                'primary_supplier'
            )
        }),
        ('Bundle Settings', {
            'fields': (
                'is_bundle',
                'bundle_type',
                'bundle_group',
                'bundle_components'
            )
        }),
        ('Pricing', {
            'fields': (
                'cost_price',
                'selling_price',
                'wholesale_price'
            )
        }),
        ('Inventory', {
            'fields': (
                'unit',
                'quantity',
                'min_stock',
                'items_per_purchase_unit',
                'purchase_unit_name'
            )
        }),
        ('Additional Info', {
            'fields': (
                'compatible_models',
                'is_active',
                'created_at',
                'updated_at'
            )
        })
    )
    
    filter_horizontal = ['bundle_components']


# ===========================
# 4. StockMovement Admin
# ===========================
@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = [
        'product',
        'movement_type',
        'quantity',
        'unit_cost',
        'balance_after',
        'reference',
        'created_at'
    ]
    
    list_filter = ['movement_type', 'created_at']
    search_fields = ['product__sku', 'product__name', 'reference', 'note']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Movement Information', {
            'fields': (
                'product',
                'movement_type',
                'quantity',
                'unit_cost',
                'balance_after'
            )
        }),
        ('Reference', {
            'fields': (
                'reference',
                'note',
                'created_at'
            )
        })
    )


# ===========================
# 5. Transaction Admin
# ===========================
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'doc_no',
        'doc_type',
        'transaction_date',
        'grand_total',
        'status',
        'created_by',
        'created_at'
    ]
    
    list_filter = ['doc_type', 'status', 'transaction_date', 'created_by']
    search_fields = ['doc_no', 'ref_doc_no', 'remark']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-transaction_date']
    
    fieldsets = (
        ('Document Information', {
            'fields': (
                'doc_type',
                'doc_no',
                'ref_doc_no',
                'transaction_date',
                'status'
            )
        }),
        ('Amount', {
            'fields': (
                'total_amount',
                'discount_amount',
                'grand_total'
            )
        }),
        ('Additional Info', {
            'fields': (
                'remark',
                'created_by',
                'created_at',
                'updated_at'
            )
        })
    )


# ===========================
# 6. TransactionItem Admin
# ===========================
@admin.register(TransactionItem)
class TransactionItemAdmin(admin.ModelAdmin):
    list_display = [
        'transaction',
        'product',
        'quantity',
        'unit_price',
        'cost_price',
        'line_total',
        'unit_type'
    ]
    
    list_filter = ['transaction__doc_type', 'unit_type']
    search_fields = [
        'transaction__doc_no',
        'product__sku',
        'product__name',
        'display_sku'
    ]
    
    fieldsets = (
        ('Transaction', {
            'fields': (
                'transaction',
                'product',
                'display_sku'
            )
        }),
        ('Quantity & Price', {
            'fields': (
                'quantity',
                'unit_type',
                'unit_price',
                'cost_price',
                'line_total'
            )
        }),
        ('Bundle Info', {
            'fields': ('bundle_items',)
        })
    )


# ===========================
# 7. Payment Admin
# ===========================
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'transaction',
        'method',
        'amount',
        'received',
        'change',
        'status',
        'created_at'
    ]
    
    list_filter = ['method', 'status', 'created_at']
    search_fields = ['transaction__doc_no', 'note']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Payment Information', {
            'fields': (
                'transaction',
                'method',
                'status'
            )
        }),
        ('Amount Details', {
            'fields': (
                'amount',
                'received',
                'change'
            )
        }),
        ('Additional Info', {
            'fields': (
                'note',
                'created_at',
                'updated_at'
            )
        })
    )


# ===========================
# 8. Purchase Admin
# ===========================
@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = [
        'doc_no',
        'supplier',
        'purchase_date',
        'grand_total',
        'status',
        'created_by',
        'created_at'
    ]
    
    list_filter = ['status', 'supplier', 'purchase_date', 'created_by']
    search_fields = ['doc_no', 'remark']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-purchase_date']
    
    fieldsets = (
        ('Purchase Information', {
            'fields': (
                'doc_no',
                'supplier',
                'purchase_date',
                'status'
            )
        }),
        ('Amount', {
            'fields': ('grand_total',)
        }),
        ('Additional Info', {
            'fields': (
                'remark',
                'created_by',
                'created_at',
                'updated_at'
            )
        })
    )


# ===========================
# 9. PurchaseItem Admin
# ===========================
@admin.register(PurchaseItem)
class PurchaseItemAdmin(admin.ModelAdmin):
    list_display = [
        'purchase',
        'product',
        'quantity',
        'unit_cost',
        'actual_stock',
        'line_total'
    ]
    
    search_fields = [
        'purchase__doc_no',
        'product__sku',
        'product__name'
    ]
    
    fieldsets = (
        ('Purchase', {
            'fields': (
                'purchase',
                'product'
            )
        }),
        ('Quantity & Cost', {
            'fields': (
                'quantity',
                'unit_cost',
                'actual_stock',
                'line_total'
            )
        })
    )


# ===========================
# 10. SystemSetting Admin
# ===========================
@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ['key', 'value']
    search_fields = ['key', 'value']
    ordering = ['key']
    
    fieldsets = (
        ('Setting', {
            'fields': ('key', 'value')
        }),
    )