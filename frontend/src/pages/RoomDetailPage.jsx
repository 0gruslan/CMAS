import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getRoom, assignRoom, evictRoom } from '../api/rooms'
import { getUsers } from '../api/users'
import { useAuth } from '../context/AuthContext'
import Layout from '../components/Layout'
import StatusBadge from '../components/StatusBadge'
import StudentSearch from '../components/StudentSearch'
import { ArrowLeft, UserPlus, UserMinus } from 'lucide-react'

export default function RoomDetailPage() {
  const { id } = useParams()
  const { isStaff } = useAuth()
  const [room, setRoom] = useState(null)
  const [residents, setResidents] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('assign')
  const [assignForm, setAssignForm] = useState({ student_id: '', check_in_date: '' })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState({ text: '', ok: true })
  const [confirmEvict, setConfirmEvict] = useState(null) // { id, name }

  const load = async () => {
    const [roomData, usersData] = await Promise.all([getRoom(id), getUsers({ room_id: id })])
    setRoom(roomData)
    setResidents(usersData)
    setLoading(false)
  }
  useEffect(() => { load() }, [id])

  const handleAssign = async e => {
    e.preventDefault(); setSaving(true); setMsg({ text: '', ok: true })
    try {
      await assignRoom({ student_id: Number(assignForm.student_id), room_id: Number(id), ...(assignForm.check_in_date ? { check_in_date: assignForm.check_in_date } : {}) })
      setMsg({ text: 'Студент успешно заселён', ok: true }); setAssignForm({ student_id: '', check_in_date: '' }); load()
    } catch (err) { setMsg({ text: err.response?.data?.detail ?? 'Ошибка', ok: false }) }
    finally { setSaving(false) }
  }

  const handleEvict = async (studentId) => {
    setSaving(true); setMsg({ text: '', ok: true })
    try {
      await evictRoom({ student_id: studentId, room_id: Number(id) })
      setMsg({ text: 'Студент выселен', ok: true }); load()
    } catch (err) { setMsg({ text: err.response?.data?.detail ?? 'Ошибка', ok: false }) }
    finally { setSaving(false) }
  }

  if (loading) return <Layout><div className="spinner-wrap"><div className="spinner" /></div></Layout>
  if (!room)   return <Layout><p style={{ color: '#94a3b8' }}>Комната не найдена</p></Layout>

  const pct = ((room.capacity - room.free_places) / room.capacity) * 100

  return (
    <Layout>
      <div style={{ maxWidth: 520 }}>
        <Link to="/rooms" className="back-link"><ArrowLeft size={14} />Назад к комнатам</Link>

        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <h1 style={{ fontSize: 20, fontWeight: 700, color: '#1e293b' }}>Комната {room.number}</h1>
              <p style={{ fontSize: 13, color: '#94a3b8', marginTop: 2 }}>Этаж {room.floor_id}</p>
            </div>
            <StatusBadge status={room.status} />
          </div>

          <div className="grid-3" style={{ marginBottom: 16, gap: 10 }}>
            {[
              { label: 'Вместимость', value: room.capacity },
              { label: 'Занято',      value: room.capacity - room.free_places },
              { label: 'Свободно',    value: room.free_places },
            ].map(({ label, value }) => (
              <div key={label} style={{ background: '#f8fafc', borderRadius: 12, padding: '12px 16px', textAlign: 'center' }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>{value}</div>
                <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{label}</div>
              </div>
            ))}
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#94a3b8', marginBottom: 6 }}>
              <span>Заполненность</span><span style={{ color: '#475569', fontWeight: 500 }}>{Math.round(pct)}%</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${pct}%`, background: pct >= 100 ? '#ef4444' : pct >= 70 ? '#f59e0b' : '#6366f1' }} />
            </div>
          </div>
        </div>

        {isStaff && (
          <div className="card">
            <div className="tab-group" style={{ marginBottom: 20, width: '100%' }}>
              {[{ key: 'assign', label: 'Заселить', Icon: UserPlus }, { key: 'evict', label: 'Выселить', Icon: UserMinus }].map(({ key, label, Icon }) => (
                <button key={key} onClick={() => { setTab(key); setMsg({ text: '', ok: true }) }}
                  className={`tab${tab === key ? ' active' : ''}`} style={{ flex: 1 }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Icon size={13} />{label}</span>
                </button>
              ))}
            </div>

            {msg.text && (
              <div className={msg.ok ? 'alert-success' : 'alert-error'} style={{ marginBottom: 16 }}>
                {msg.ok ? '✓' : '⚠'} {msg.text}
              </div>
            )}

            {tab === 'assign' ? (
              <form onSubmit={handleAssign} className="stack">
                <FL label="Студент">
                  <StudentSearch
                    value={assignForm.student_id}
                    onChange={id => setAssignForm({ ...assignForm, student_id: id })}
                  />
                </FL>
                <FL label="Дата заезда (необязательно)">
                  <input type="date" value={assignForm.check_in_date}
                    onChange={e => setAssignForm({ ...assignForm, check_in_date: e.target.value })}
                    className="field" />
                </FL>
                <button type="submit" disabled={saving || !assignForm.student_id} className="btn btn-primary w-full">
                  <UserPlus size={14} />{saving ? 'Заселение...' : 'Заселить'}
                </button>
              </form>
            ) : (
              <div className="stack">
                {residents.length === 0 ? (
                  <p style={{ color: '#94a3b8', fontSize: 13, textAlign: 'center', padding: '12px 0' }}>Жильцов нет</p>
                ) : (
                  <div className="stack-sm">
                    {residents.map(r => (
                      <div key={r.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderRadius: 12, background: '#fafafa' }}>
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 500, color: '#1e293b' }}>{r.full_name}</div>
                          <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{r.email}</div>
                        </div>
                        <button onClick={() => setConfirmEvict({ id: r.id, name: r.full_name })} disabled={saving} className="btn btn-danger" style={{ padding: '6px 12px', fontSize: 12 }}>
                          <UserMinus size={12} />Выселить
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {confirmEvict && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={() => setConfirmEvict(null)}>
          <div style={{ background: '#fff', borderRadius: 16, padding: 28, width: 340, boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: '#fef2f2', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <UserMinus size={16} style={{ color: '#ef4444' }} />
              </div>
              <div style={{ fontSize: 15, fontWeight: 600, color: '#1e293b' }}>Подтверждение выселения</div>
            </div>
            <p style={{ fontSize: 13, color: '#64748b', marginBottom: 20, lineHeight: 1.5 }}>
              Вы уверены, что хотите выселить <strong style={{ color: '#1e293b' }}>{confirmEvict.name}</strong>? Это действие нельзя отменить.
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => setConfirmEvict(null)} className="btn" style={{ flex: 1, background: '#f1f5f9', color: '#475569' }}>
                Отмена
              </button>
              <button disabled={saving} className="btn btn-danger" style={{ flex: 1 }} onClick={() => { handleEvict(confirmEvict.id); setConfirmEvict(null) }}>
                <UserMinus size={13} />{saving ? 'Выселение...' : 'Выселить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  )
}

function FL({ label, children }) {
  return <div><label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: '#374151', marginBottom: 6 }}>{label}</label>{children}</div>
}
