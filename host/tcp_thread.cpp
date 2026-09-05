#include "tcp_thread.h"
#include <QDebug>

Tcp_Thread::Tcp_Thread(QHostAddress ip, QString port, QObject *parent) : QThread(parent)
{
    start_flag = true;
    connect_flag = false;
    recv_flag = false;
    _paused = false;

    server = new QTcpServer();
    server->listen(ip, port.toInt());
    connect(server, &QTcpServer::newConnection, this, &Tcp_Thread::on_new_connection);
}

void Tcp_Thread::run()
{
    while (start_flag) {
        // 暂停检查：被 stop() 挂起时阻塞在此，不空转
        {
            QMutexLocker pl(&_pauseMutex);
            while (_paused) {
                _pauseCond.wait(&_pauseMutex);
                if (!start_flag) break;
            }
        }

        // 把缓冲中的完整行（以 \n 结尾）拆成消息
        bool any = false;
        {
            QMutexLocker ql(&_queueMutex);
            int idx;
            while ((idx = _recvBuf.indexOf('\n')) >= 0) {
                QByteArray line = _recvBuf.left(idx);
                _recvBuf.remove(0, idx + 1);
                QString msg = QString::fromUtf8(line).trimmed();
                if (!msg.isEmpty()) {
                    _msgQueue.enqueue(msg);
                    any = true;
                }
            }
        }
        if (any && start_flag)
            emit signal_msg();

        msleep(5);
    }
}

void Tcp_Thread::on_new_connection()
{
    socket = server->nextPendingConnection();
    client_ip = socket->peerAddress();
    client_port = socket->peerPort();
    connect(socket, SIGNAL(readyRead()), this, SLOT(on_ready_read()));
    connect(socket, SIGNAL(disconnected()), this, SLOT(on_disconnected()));
    connect_flag = true;
    {
        QMutexLocker ql(&_queueMutex);
        _msgQueue.enqueue(QString("上线 [%1]").arg(client_ip.toString()));
    }
    emit signal_msg();
}

// 主线程槽：读取客户端数据到分帧缓冲
void Tcp_Thread::on_ready_read()
{
    if (!socket || !recv_flag)
        return;
    QByteArray data = socket->readAll();
    if (data.isEmpty())
        return;
    QMutexLocker ql(&_queueMutex);
    _recvBuf += data;
}

void Tcp_Thread::on_disconnected()
{
    connect_flag = false;
    {
        QMutexLocker ql(&_queueMutex);
        _msgQueue.enqueue(QString("已断开！"));
    }
    emit signal_msg();
}

bool Tcp_Thread::has_msg()
{
    QMutexLocker l(&_queueMutex);
    return !_msgQueue.isEmpty();
}
QString Tcp_Thread::take_msg()
{
    QMutexLocker l(&_queueMutex);
    return _msgQueue.dequeue();
}

void Tcp_Thread::stop()   { QMutexLocker l(&_pauseMutex); _paused = true; }
void Tcp_Thread::go_on()  { QMutexLocker l(&_pauseMutex); _paused = false; _pauseCond.wakeAll(); }

Tcp_Thread::~Tcp_Thread()
{
    if (socket) {
        socket->abort();
        delete socket;
        socket = nullptr;
    }
    if (server) {
        server->close();
        delete server;
        server = nullptr;
    }
}
