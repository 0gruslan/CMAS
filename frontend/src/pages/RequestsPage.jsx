import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRequests, createRequest, deleteRequest } from '../api/requests'
import { useAuth } from '../context/AuthContext'
import Layout from '../components/Layout'
import StatusBadge from '../components/StatusBadge'
import { Plus, X, ChevronRight, ClipboardList, AlertTriangle, Trash2 } from 'lucide-react'

const CATEGORIES = ['Сантехника', 'Электрика', 'Интернет', 'Мебель', 'Уборка', 'Другое']
const CAT_COLOR = { 'Сантехника': '#3b82f6', 'Электрика': '#f59e0b', 'Интернет': '#8b5cf6', 'Мебель': '#10b981', 'Уборка': '#06b6d4', 'Другое': '#94a3b8' }
const FILTERS = [{ value: '', label: 'Все' }, { value: 'created', label: 'Создана' }, { value: 'in_progress', label: 'В работе' }, { value: 'done', label: 'Выполнена' }]

export default function RequestsPage() {
  const { user, isStaff } = useAuth()
  const [requests, setRequests] = useState([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ category: CATEGORIES[0], description: '', room_id: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null) // { id, category }

  // Для студента комната берётся из профиля автоматически
  const studentRoomId = !isStaff ? user?.room_id : null
  const studentHasNoRoom = !isStaff && !studentRoomId

  const load = () => getRequests(filter ? { status: filter } : {}).then(setRequests).finally(() => setLoading(false))
  useEffect(() => { load() }, [filter])

  const openModal = () => {
    if (studentHasNoRoom) return
    setError('')
    // Для студента room_id = его комната
    setForm({ category: CATEGORIES[0], description: '', room_id: isStaff ? '' : String(studentRoomId) })
    setShowModal(true)
  }

  const handleCreate = async e => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await createRequest({
        student_id: user.id,
        room_id: Number(form.room_id),
        category: form.category,
        description: form.description,
      })
      setShowModal(false)
      load()
    } catch (err) {
      const detail = err.response?.data?.detail
      if (!detail) setError('Ошибка при создании заявки')
      else if (typeof detail === 'string') setError(detail)
      else if (Array.isArray(detail)) setError(detail.map(d => d.msg).join('; '))
      else setError('Ошибка при создании заявки')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) return
    try {
      await deleteRequest(confirmDelete.id)
      setConfirmDelete(null)
      load()
    } catch { /* ignore */ }
  }

  return (
    <Layout>
      <div className="page-header row-between">
        <div>
          <h1 className="page-title">{isStaff ? 'Заявки на обслуживание' : 'Мои заявки'}</h1>
          <p className="page-subtitle">{requests.length} заявок</p>
        </div>
        {/* Студент без комнаты не может создавать заявки */}
        {studentHasNoRoom ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#d97706', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 10, padding: '7px 12px' }}>
            <AlertTriangle size={14} />
            Вы не прикреплены к комнате
          </div>
        ) : (
          <button onClick={openModal} className="btn btn-primary btn-sm">
            <Plus size={14} />Создать заявку
          </button>
        )}
      </div>

      {/* Filter tabs */}
      <div className="filter-tabs" style={{ marginBottom: 16 }}>
        {FILTERS.map(({ value, label }) => (
          <button key={value} onClick={() => setFilter(value)}
            className={`filter-tab${filter === value ? ' active' : ''}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading
          ? <div className="spinner-wrap"><div className="spinner" /></div>
          : requests.length === 0
            ? <div className="empty"><ClipboardList size={28} style={{ color: '#e2e8f0' }} /><span>Заявок нет</span></div>
            : (
              <table className="table">
                <thead><tr>
                  <th>#</th><th>Категория</th><th>Описание</th>
                  {isStaff && <th>Студент</th>}
                  <th>Статус</th><th>Дата</th><th style={{ width: isStaff ? 64 : 36 }}></th>
                </tr></thead>
                <tbody>
                  {requests.map(req => (
                    <tr key={req.id}>
                      <td style={{ color: '#cbd5e1', fontSize: 12, fontFamily: 'monospace' }}>{req.id}</td>
                      <td>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 500, color: '#1e293b' }}>
                          <span style={{ width: 6, height: 6, borderRadius: '50%', background: CAT_COLOR[req.category] ?? '#94a3b8', flexShrink: 0 }} />
                          {req.category}
                        </span>
                      </td>
                      <td style={{ fontSize: 13, color: '#64748b', maxWidth: 220 }}>
                        <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{req.description}</span>
                      </td>
                      {isStaff && <td style={{ fontSize: 13, color: '#94a3b8' }}>#{req.student_id}</td>}
                      <td><StatusBadge status={req.status} /></td>
                      <td style={{ fontSize: 12, color: '#94a3b8', whiteSpace: 'nowrap' }}>
                        {new Date(req.created_at).toLocaleDateString('ru-RU')}
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          {isStaff && (
                            <button onClick={() => setConfirmDelete({ id: req.id, category: req.category })}
                              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, borderRadius: 8, color: '#fca5a5', background: 'transparent', border: 'none', cursor: 'pointer' }}
                              onMouseEnter={e => { e.currentTarget.style.background = '#fef2f2'; e.currentTarget.style.color = '#ef4444' }}
                              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#fca5a5' }}>
                              <Trash2 size={13} />
                            </button>
                          )}
                          <Link to={`/requests/${req.id}`}
                            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, borderRadius: 8, color: '#cbd5e1', textDecoration: 'none' }}
                            onMouseEnter={e => { e.currentTarget.style.background = '#eef2ff'; e.currentTarget.style.color = '#6366f1' }}
                            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#cbd5e1' }}>
                            <ChevronRight size={14} />
                          </Link>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
      </div>

      {confirmDelete && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={() => setConfirmDelete(null)}>
          <div style={{ background: '#fff', borderRadius: 16, padding: 28, width: 340, boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: '#fef2f2', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Trash2 size={16} style={{ color: '#ef4444' }} />
              </div>
              <div style={{ fontSize: 15, fontWeight: 600, color: '#1e293b' }}>Удалить заявку</div>
            </div>
            <p style={{ fontSize: 13, color: '#64748b', marginBottom: 20, lineHeight: 1.5 }}>
              Вы уверены, что хотите удалить заявку <strong style={{ color: '#1e293b' }}>#{confirmDelete.id} · {confirmDelete.category}</strong>? Это действие нельзя отменить.
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => setConfirmDelete(null)} className="btn" style={{ flex: 1, background: '#f1f5f9', color: '#475569' }}>
                Отмена
              </button>
              <button onClick={handleDelete} className="btn btn-danger" style={{ flex: 1 }}>
                <Trash2 size={13} />Удалить
              </button>
            </div>
          </div>
        </div>
      )}

      {showModal && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16, background: 'rgba(15,23,42,0.4)', backdropFilter: 'blur(4px)' }}>
          <div style={{ background: 'white', borderRadius: 20, boxShadow: '0 20px 60px rgba(0,0,0,0.15)', width: '100%', maxWidth: 440, padding: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <span style={{ fontWeight: 600, fontSize: 15, color: '#1e293b' }}>Новая заявка</span>
              <button onClick={() => setShowModal(false)} className="btn btn-ghost" style={{ padding: 6 }}><X size={16} /></button>
            </div>

            <form onSubmit={handleCreate} className="stack">
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: '#374151', marginBottom: 6 }}>Категория</label>
                <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}
                  className="field" style={{ appearance: 'none', width: '100%' }}>
                  {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>

              {/* Комната: для студента показываем readonly, для staff — вводят вручную */}
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: '#374151', marginBottom: 6 }}>Комната</label>
                {isStaff ? (
                  <input type="number" required value={form.room_id}
                    onChange={e => setForm({ ...form, room_id: e.target.value })}
                    className="field" placeholder="ID комнаты" />
                ) : (
                  <div className="field" style={{ background: '#f8fafc', color: '#64748b', cursor: 'default' }}>
                    Комната #{studentRoomId}
                  </div>
                )}
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: '#374151', marginBottom: 6 }}>Описание</label>
                <textarea required minLength={5} rows={4} value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  className="field" style={{ resize: 'none', width: '100%' }}
                  placeholder="Опишите проблему подробно (минимум 5 символов)..." />
              </div>

              {error && <div className="alert-error"><span>⚠</span><span>{error}</span></div>}

              <div className="row">
                <button type="submit" disabled={saving} className="btn btn-primary">
                  {saving ? 'Отправка...' : 'Отправить'}
                </button>
                <button type="button" onClick={() => setShowModal(false)} className="btn btn-ghost">Отмена</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </Layout>
  )
}
