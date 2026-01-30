# MDM/OE Coordinator - UI Assignment Guide

## How to Assign MDM/OE Coordinator Role

### Step-by-Step Process

#### 1. Login as Admin
- Navigate to `http://localhost:5000`
- Login with admin credentials

#### 2. Navigate to Roles & Permissions
**Option A - Via Sidebar:**
- Click **"Roles & Permissions"** under the **Staff** section

**Option B - Direct URL:**
- Go to `http://localhost:5000/admin/manage_coordinators`

#### 3. Assign the Role
You'll see a table with all faculty members and role toggles:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Faculty Name          │ Event Coord │ AMC Member │ AMC Head │ MDM/OE Coord│
├──────────────────────────────────────────────────────────────────────────┤
│ Dr. John Smith        │     ✓       │     -      │    -     │      -      │
│ EMP001 • Computing    │             │            │          │             │
├──────────────────────────────────────────────────────────────────────────┤
│ Dr. Jane Doe          │     -       │     ✓      │    -     │      ✓      │
│ EMP002 • Computing    │             │            │          │  [GREEN]    │
└──────────────────────────────────────────────────────────────────────────┘
```

**Toggle Button States:**
- **Gray with dash (-)** = Role NOT assigned
- **Green with checkmark (✓)** = MDM/OE Coordinator assigned
- **Purple with checkmark** = Event Coordinator assigned
- **Blue with checkmark** = AMC Member assigned
- **Yellow with crown** = AMC Head assigned

#### 4. Click the Toggle
- Find the faculty member you want to assign
- Click the **circular button** under the **"MDM/OE Coord"** column
- The button will turn **green** and show a **checkmark (✓)**
- Role is immediately assigned (auto-saves)

#### 5. Access MDM/OE Dashboard
Once assigned, the coordinator can access the dashboard:

**Method 1 - Sidebar Link:**
- In the Admin Dashboard sidebar, under **System** section
- Click **"MDM/OE Cross-School"**

**Method 2 - Direct URL:**
- Navigate to `/admin/mdm_oe_coordinator`

---

## UI Screenshots (Visual Reference)

### Admin Sidebar - New Link
```
┌─────────────────────────────┐
│  📊 ADMIN                   │
├─────────────────────────────┤
│  Main                       │
│  ▪ Overview                 │
│                             │
│  Academics                  │
│  ▪ Classes                  │
│  ▪ Students                 │
│  ▪ Promotions               │
│  ▪ Timetable                │
│                             │
│  Staff                      │
│  ▪ Faculty Directory        │
│  ▪ Roles & Permissions      │
│                             │
│  System                     │
│  ▪ 🌐 MDM/OE Cross-School  │ ← NEW LINK
│  ▪ Academic Archives        │
└─────────────────────────────┘
```

### Roles & Permissions Table
```
┌───────────────────────────────────────────────────────────────────────┐
│  Assign Additional Roles                      [Search Faculty...]    │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Faculty Name         │ Event   │ AMC     │ AMC   │ MDM/OE          │
│                       │ Coord   │ Member  │ Head  │ Coord           │
│  ─────────────────────┼─────────┼─────────┼───────┼─────────────    │
│  Dr. Alice Johnson    │   (-)   │   (-)   │  (-)  │  (✓) GREEN     │
│  EMP001 • Computing   │ GRAY    │ GRAY    │ GRAY  │                │
│  ─────────────────────┼─────────┼─────────┼───────┼─────────────    │
│  Prof. Bob Williams   │   (✓)   │   (-)   │  (-)  │  (-)           │
│  EMP002 • Computing   │ PURPLE  │ GRAY    │ GRAY  │ GRAY           │
└───────────────────────────────────────────────────────────────────────┘

* Note: Only one faculty member can be assigned as AMC Head at a time.
```

### MDM/OE Coordinator Dashboard
```
┌────────────────────────────────────────────────────────────────────────┐
│  MDM / OE Coordinator Dashboard                                       │
│  Cross-School Course Management                [← Back] [Logout]      │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│  │ Inbound    │  │ Outbound   │  │ External   │  │ Our        │    │
│  │ Offerings  │  │ Offerings  │  │ Students   │  │ Students   │    │
│  │    3       │  │    2       │  │    45      │  │    12      │    │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘    │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ [Inbound Offerings] [Outbound Offerings] [+ Create Offering] │    │
│  ├──────────────────────────────────────────────────────────────┤    │
│  │                                                               │    │
│  │  📚 Introduction to Blockchain                [Export Marks]  │    │
│  │  MDM101 | MDM | 3 Credits                                    │    │
│  │  Faculty: Dr. Alice Johnson                                  │    │
│  │  Enrolled: 45/60                                              │    │
│  │                                                               │    │
│  └──────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Role Validation

The system enforces the following:
- ✅ Backend checks `is_mdm_oe_coordinator=True` before allowing access
- ✅ Frontend hides dashboard link if user doesn't have coordinator role
- ✅ Direct URL access blocked with 403 Forbidden if not authorized
- ✅ All MDM/OE API endpoints require Admin role + coordinator flag

---

## Quick Test Checklist

- [ ] Can toggle MDM/OE Coordinator role on/off in Roles & Permissions page
- [ ] Toggle button changes color (gray ↔ green) instantly
- [ ] Sidebar link appears in Admin Dashboard under System section
- [ ] Clicking sidebar link opens MDM/OE Coordinator dashboard
- [ ] Dashboard shows 4 stat cards with zero counts initially
- [ ] Can create new offering via "Create Offering" tab
- [ ] Non-coordinators get 403 error when accessing `/admin/mdm_oe_coordinator`

---

## Troubleshooting

**Issue:** Toggle button doesn't change color
- **Solution:** Check browser console for JavaScript errors, ensure `is_mdm_oe_coordinator` is in API response

**Issue:** Sidebar link doesn't appear
- **Solution:** Clear browser cache, verify you're logged in as Admin

**Issue:** 403 Forbidden when accessing dashboard
- **Solution:** Ensure coordinator toggle is enabled for your user, check backend logs

**Issue:** "Access restricted" message on dashboard
- **Solution:** Re-toggle the coordinator role, logout and login again

---

## API Backend (Already Implemented)

The following backend code supports the UI:

**Role Toggle API:**
```python
@app.route('/api/admin/toggle_role', methods=['POST'])
# ... handles role_type='mdm_oe_coordinator'
```

**Coordinator List API:**
```python
@app.route('/api/admin/coordinators', methods=['GET'])
# ... returns is_mdm_oe_coordinator flag in response
```

**Dashboard Access Control:**
```python
@app.route('/admin/mdm_oe_coordinator')
@login_required
@require_roles('Admin')
def render_coordinator_mdm_oe():
    if not staff.is_mdm_oe_coordinator:
        return "Access restricted", 403
```

---

## Summary

✅ **UI Integration Complete**
- Toggle button in Roles & Permissions page
- Sidebar navigation link in Admin Dashboard
- Full dashboard with stats and management interface

🎯 **User Flow**
1. Admin assigns coordinator role via toggle
2. Coordinator sees sidebar link appear
3. Clicks link to access MDM/OE dashboard
4. Manages cross-school courses end-to-end

No SQL commands needed - everything is done through the web interface! 🎉
