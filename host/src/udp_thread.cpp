#include "udp_thread.h"
#include <QBuffer>
#include <QImageReader>
#include <QDir>
#include <QFileInfo>
#include <QDebug>

Udp_Thread::Udp_Thread(QHostAddress ip, QString port, QObject *parent) : QThread(parent)
{
    start_flag = true;
    recv_flag = false;
    _paused = false;

    socket = new QUdpSocket();
    socket->bind(ip, port.toInt());
    connect(socket, SIGNAL(readyRead()), this, SLOT(on_udp_ready()));
}

void Udp_Thread::run()
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

        QPixmap pix;
        {
            QMutexLocker ql(&_queueMutex);
            if (_frames.isEmpty()) {
                ql.unlock();
                msleep(5);
                continue;
            }
            pix = _frames.dequeue();
        }

        emit signal_img();   // 通知 Widget 有新帧

        // 保存请求（若有）：把当前帧存为 JPEG
        QString path;
        {
            QMutexLocker ql(&_queueMutex);
            if (_saveFlag) {
                path = _savePath;
                _saveFlag = false;
            }
        }
        if (!path.isEmpty()) {
            QDir().mkpath(QFileInfo(path).absolutePath());
            if (pix.save(path)) {
                {
                    QMutexLocker ql(&_queueMutex);
                    _saveResult = path;
                }
                emit signal_img_saved(path);
            }
        }
        msleep(2);
    }
}

// 主线程槽：收取 UDP 数据报并解码（阻塞极短，仅拷到队列）
void Udp_Thread::on_udp_ready()
{
    if (!socket || !recv_flag)
        return;
    QByteArray buff;
    buff.resize(socket->pendingDatagramSize());
    socket->readDatagram(buff.data(), buff.size());

    QBuffer img_buffer(&buff);
    QImageReader reader(&img_buffer, "JPEG");
    QPixmap pix = QPixmap::fromImage(reader.read());
    if (pix.isNull())
        return;
    QMutexLocker ql(&_queueMutex);
    while (_frames.size() >= MAX_FRAMES)   // 限流：丢弃最旧帧，防止积压
        _frames.dequeue();
    _frames.enqueue(pix);
}

bool Udp_Thread::has_frame()       { QMutexLocker l(&_queueMutex); return !_frames.isEmpty(); }
QPixmap Udp_Thread::take_frame()   { QMutexLocker l(&_queueMutex); return _frames.dequeue(); }

void Udp_Thread::request_save(const QString &path)
{
    QMutexLocker l(&_queueMutex);
    _savePath = path;
    _saveFlag = true;
}

QString Udp_Thread::take_save_result()
{
    QMutexLocker l(&_queueMutex);
    QString r = _saveResult;
    _saveResult.clear();
    return r;
}

void Udp_Thread::stop()   { QMutexLocker l(&_pauseMutex); _paused = true; }
void Udp_Thread::go_on()  { QMutexLocker l(&_pauseMutex); _paused = false; _pauseCond.wakeAll(); }

Udp_Thread::~Udp_Thread()
{
    if (socket) {
        socket->close();
        delete socket;
        socket = nullptr;
    }
}
