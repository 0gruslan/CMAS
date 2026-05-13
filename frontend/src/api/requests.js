import client from './client'

export const getRequests = (params) =>
  client.get('/requests', { params }).then((r) => r.data)

export const getRequest = (id) =>
  client.get(`/requests/${id}`).then((r) => r.data)

export const createRequest = (data) =>
  client.post('/requests', data).then((r) => r.data)

export const updateRequestStatus = (id, data) =>
  client.put(`/requests/${id}/status`, data).then((r) => r.data)

export const addComment = (id, data) =>
  client.post(`/requests/${id}/comments`, data).then((r) => r.data)

export const deleteRequest = (id) =>
  client.delete(`/requests/${id}`)
