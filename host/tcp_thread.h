#ifndef TCP_THREAD_H
#define TCP_THREAD_H

#include <QThread>
#include <QHostAddress>
#include <QQueue>
#include <QMutex>
#include <QMutexLocker>
#include <QWaitCondition>
#include <QTcpSocket>
#include <QTcpServer>

// TCP 通信线程（本上位机作为服务端，监听 9999）。
// 从客户端读到的字节按换行分帧成“消息”，队列受 _queueMutex 保护（跨线程安全）。
class Tcp_Thread : public QThread
{
    Q_OBJECT
public:
    explicit Tcp_Thread(QHostAddress ip, QString port, QObject *parent = nullptr);
    ~Tcp_Thread();

    bool start_flag;    // 线程工作标志
    bool connect_flag;  // 是否有客户端连接
    bool recv_flag;     // 是否接收数据计入队列

    QTcpSocket *socket = nullptr;  // 客户端套接字
    QTcpServer *server = nullptr;

    QHostAddress client_ip;
    qint16 client_port = 0;

    void stop();        // 暂停线程
    void go_on();       // 继续线程

    // 线程安全取消息
    bool has_msg();
    QString take_msg();

protected:
    void run();

signals:
    void signal_msg();

private:
    QMutex _queueMutex;             // 保护 _msgQueue / _recvBuf
    QQueue<QString> _msgQueue;
    QByteArray _recvBuf;            // 跨 recv 的换行分帧缓冲

    QMutex _pauseMutex;             // 暂停/继续
    QWaitCondition _pauseCond;
    bool _paused = false;

private slots:
    void on_new_connection();
    void on_ready_read();
    void on_disconnected();
};

#endif // TCP_THREAD_H
